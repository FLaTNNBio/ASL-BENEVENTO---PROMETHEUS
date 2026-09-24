# -*- coding: utf-8 -*-
"""
allocator_cp_sat.py — versione pulita con:
- Budget medici 24/7 e mappa per tipo (--staff-per-type)
- Budget infermieri 24/7 e mappa per tipo (--nurses-per-type)
- Impatto OPEX degli infermieri via --nurse-unit-opex
- Coupling trasporto: AUTO_MED richiede almeno un'AMB (ALS/ILS) (base|global)
- Vincoli PSAUT (min/exact) con slack
- Budget costi (CAPEX+OPEX) 'purchase' o 'all'
- Modalità "doctor-cover" per codici ROSSO,GIALLO,VERDE,BIANCO (strict/feasible/off)
- Multi-caso da CSV e sweep del budget medici

Output: chosen_slots.csv, coverage_summary.csv, doctor_coverage_summary.csv,
        doctors_summary.txt, feasibility_report.txt, feasibility_summary.csv, run_summary.csv
"""

import argparse
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# -------------------- Costanti e utils --------------------

KNOWN_TYPES = {"AUTO_MED", "AMB_ALS", "AMB_ILS", "PSAUT", "CMR"}
CODES = ["ROSSO", "GIALLO", "VERDE", "BIANCO"]
CODE_IDX = {c: i for i, c in enumerate(CODES)}
DEFAULT_THRESH = {"ROSSO": 8.0, "GIALLO": 20.0, "VERDE": 30.0, "BIANCO": 45.0}

TYPE_SYNONYMS = {
    "AUTOMEDICA": "AUTO_MED",
    "AUTO MED": "AUTO_MED",
    "AUTO-MED": "AUTO_MED",
    "ALS": "AMB_ALS",
    "ILS": "AMB_ILS",
    "PS AUT": "PSAUT",
    "POSTAZIONE_AUTOMEDICA": "PSAUT",
    # --- nuove varianti per il centro mobile ---
    "CMR": "CMR",
    "CMA": "CMR",
    "CENTRO_MOBILE_DI_RIANIMAZIONE": "CMR",
    "CENTRO MOBILE DI RIANIMAZIONE": "CMR",
    "CENTRO_MOBILE_DI_ANESTESIA": "CMR",
    "CENTRO MOBILE DI ANESTESIA": "CMR",
}

def norm_commune(x: str) -> str:
    x = str(x).strip().replace("’", "'")
    x = re.sub(r"\s+", " ", x)
    return " ".join(w.capitalize() if "'" not in w else (w[0].upper() + w[1:]) for w in x.split())


def normalize_tipo(v: str) -> str:
    t = str(v).strip().upper().replace("-", "_").replace(" ", "_")
    return TYPE_SYNONYMS.get(t, t)


def parse_map(s: Optional[str], cast=float) -> Dict[str, float]:
    if not s:
        return {}
    out: Dict[str, float] = {}
    for part in str(s).split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        try:
            out[k.strip().upper()] = cast(v.strip())
        except Exception:
            pass
    return out


def parse_list_nums(s: Optional[str], cast=float) -> List[float]:
    if not s:
        return []
    vals = []
    for tok in re.split(r"[,\s;]+", str(s).strip()):
        if tok == "":
            continue
        try:
            vals.append(cast(tok))
        except Exception:
            pass
    return vals


def parse_doctor_codes(s: Optional[str]) -> List[bool]:
    req = [False, False, False, False]  # R,G,V,B
    if not s or str(s).strip() == "":
        return req
    names = [tok.strip().upper() for tok in re.split(r"[,\s;]+", str(s)) if tok.strip()]
    for i, name in enumerate(CODES):
        if name in names:
            req[i] = True
    return req


def parse_weights(s: Optional[str]) -> Dict[str, float]:
    w = {"COV": 1e9, "DOC": 8e8, "PSAUT": 8e8, "DOCTORS": 8e8, "NURSES": 8e8, "BUDGET": 8e8}
    if not s:
        return w
    user = parse_map(s, cast=float)
    for k in list(w.keys()):
        if k in user:
            w[k] = float(user[k])
    return w


# -------------------- Load input --------------------

def load_communes(data_dir: Path) -> pd.DataFrame:
    p = data_dir / "comuni.csv"
    df = pd.read_csv(p)
    if "comune" not in df.columns:
        raise SystemExit(f"{p.name} deve avere colonna 'comune'.")
    out = pd.DataFrame({"comune": df["comune"].astype(str).map(norm_commune).dropna().unique()})
    return out


def load_demand(data_dir: Path) -> pd.DataFrame:
    p_w = data_dir / "weighted_demand_by_comune_code.csv"
    p_d = data_dir / "demand_by_comune_code.csv"
    if p_w.exists():
        df = pd.read_csv(p_w)
        val_col = "n_missioni_pesate"
    elif p_d.exists():
        df = pd.read_csv(p_d)
        val_col = "n_missioni"
    else:
        raise SystemExit("Manca demand_by_comune_code.csv (o weighted_demand_by_comune_code.csv).")
    code_col = next((c for c in df.columns if str(c).lower().strip() in {"codice", "codice_invio", "colore", "code"}),
                    None)
    if code_col is None:
        raise SystemExit(f"Nessuna colonna codice in {p_w.name if p_w.exists() else p_d.name}")
    out = pd.DataFrame({
        "comune": df["comune"].astype(str).map(norm_commune),
        "codice_invio": df[code_col].astype(str).str.upper().str.strip(),
        "chiamate": pd.to_numeric(df[val_col], errors="coerce").fillna(0.0)
    })
    out = out[out["codice_invio"].isin(CODES)]
    out = out.groupby(["comune", "codice_invio"], as_index=False)["chiamate"].sum()
    return out


def load_or_build_sites(data_dir: Path) -> pd.DataFrame:
    p = data_dir / "sites.csv"
    if p.exists():
        df = pd.read_csv(p)
        cols = set(df.columns)
        if {"site_id", "tipo", "is_fixed", "fixed_commune"}.issubset(cols):
            out = df.copy()
            out["tipo"] = out["tipo"].map(normalize_tipo)
            out["is_fixed"] = pd.to_numeric(out["is_fixed"], errors="coerce").fillna(0).astype(int)
            out["fixed_commune"] = out["fixed_commune"].astype(str).map(
                lambda x: norm_commune(x) if str(x).strip() != "" else "")
            out = out[out["tipo"].isin(KNOWN_TYPES)]
            if out.empty:
                raise SystemExit("sites.csv non contiene tipi noti.")
            return out[{"site_id", "tipo", "is_fixed", "fixed_commune"}]
        if {"comune", "tipo_presidio"}.issubset(cols):
            tmp = df.copy()
            tmp["site_id"] = [f"FIX_{i + 1:03d}" for i in range(len(tmp))]
            tmp["tipo"] = tmp["tipo_presidio"].map(normalize_tipo)
            tmp["is_fixed"] = 1
            tmp["fixed_commune"] = tmp["comune"].astype(str).map(norm_commune)
            tmp = tmp[tmp["tipo"].isin(KNOWN_TYPES)]
            return tmp[["site_id", "tipo", "is_fixed", "fixed_commune"]]
        if "comune" in cols:  # assume ILS
            tmp = df.copy()
            tmp["site_id"] = [f"FIX_{i + 1:03d}" for i in range(len(tmp))]
            tmp["tipo"] = "AMB_ILS"
            tmp["is_fixed"] = 1
            tmp["fixed_commune"] = tmp["comune"].astype(str).map(norm_commune)
            return tmp[["site_id", "tipo", "is_fixed", "fixed_commune"]]
        raise SystemExit(f"sites.csv presente ma colonne non riconosciute: {list(df.columns)}")

    # fallback: presidi_* o sites_geocoded.csv
    rows = []
    sid = 1
    p_att = data_dir / "presidi_attuali.csv"
    if p_att.exists():
        att = pd.read_csv(p_att)
        if {"comune", "tipo_presidio"}.issubset(att.columns):
            for _, r in att.iterrows():
                tipo = normalize_tipo(r["tipo_presidio"])
                if tipo in KNOWN_TYPES:
                    rows.append({"site_id": f"FIX_{sid:03d}", "tipo": tipo, "is_fixed": 1,
                                 "fixed_commune": norm_commune(r["comune"])})
                    sid += 1
    p_pot = data_dir / "presidi_potenziali.csv"
    if p_pot.exists():
        pot = pd.read_csv(p_pot)
        if "comune" in pot.columns:
            for _, r in pot.iterrows():
                rows.append({"site_id": f"MOB_{sid:03d}", "tipo": "AMB_ILS", "is_fixed": 0,
                             "fixed_commune": norm_commune(r["comune"])})
                sid += 1
    if rows:
        return pd.DataFrame(rows)

    p_geo = data_dir / "sites_geocoded.csv"
    if p_geo.exists():
        g = pd.read_csv(p_geo)
        if "comune" not in g.columns:
            raise SystemExit("sites_geocoded.csv deve avere 'comune'.")
        tipo_col = "tipo_presidio" if "tipo_presidio" in g.columns else ("tipo" if "tipo" in g.columns else None)
        rows = []
        sid = 1
        for _, r in g.iterrows():
            comune = norm_commune(r["comune"])
            tipo = normalize_tipo(r[tipo_col]) if tipo_col else "AMB_ILS"
            if tipo not in KNOWN_TYPES:
                continue
            rows.append({"site_id": f"FIX_{sid:03d}", "tipo": tipo, "is_fixed": 1, "fixed_commune": comune})
            sid += 1
        if rows:
            return pd.DataFrame(rows)
    raise SystemExit("Impossibile costruire sites (mancano sites.csv/presidi_*/sites_geocoded.csv).")


def load_od_any(data_dir: Path, sites_df: pd.DataFrame) -> pd.DataFrame:
    p = data_dir / "od_time_min.csv"
    df = pd.read_csv(p)
    cols = {c.lower(): c for c in df.columns}

    def pick(cands):
        for k in cands:
            if k in cols:
                return cols[k]
        return None

    origin = pick(["origin_comune", "from_comune", "origin", "from"])
    dest = pick(["dest_comune", "to_comune", "destination", "dest", "to"])
    tcol = pick(["travel_time_min", "time_min", "tempo_min", "minuti", "minutes"])

    if origin and dest and tcol:
        out = pd.DataFrame({
            "origin_comune": df[origin].astype(str).map(norm_commune),
            "dest_comune": df[dest].astype(str).map(norm_commune),
            "travel_time_min": pd.to_numeric(df[tcol], errors="coerce")
        }).dropna(subset=["origin_comune", "dest_comune", "travel_time_min"])
        return out

    need = {"from_site_id", "to_comune"}
    if not need.issubset(set(df.columns)) or tcol is None:
        raise SystemExit(f"Impossibile dedurre colonne OD in {p.name}: {list(df.columns)}")

    if not {"site_id", "fixed_commune"}.issubset(set(sites_df.columns)):
        raise SystemExit("Per OD sito->comune serve sites con site_id,fixed_commune.")
    s2c = dict(zip(sites_df["site_id"].astype(str), sites_df["fixed_commune"].astype(str)))
    df["_origin_comune"] = df["from_site_id"].astype(str).map(s2c)
    out = pd.DataFrame({
        "origin_comune": df["_origin_comune"].astype(str).map(norm_commune),
        "dest_comune": df["to_comune"].astype(str).map(norm_commune),
        "travel_time_min": pd.to_numeric(df[tcol], errors="coerce")
    }).dropna(subset=["origin_comune", "dest_comune", "travel_time_min"])
    out = out.groupby(["origin_comune", "dest_comune"], as_index=False)["travel_time_min"].min()
    return out


# -------------------- Famiglie di riloc --------------------

def build_reloc_families(
        sites_alloc: pd.DataFrame,
        communes_alloc: pd.DataFrame,
        presidi_att: Path,
        presidi_pot: Path,
        od_alloc: pd.DataFrame,
        bases_mode: str = "ATT_POT",
        limit_bases: int = 0,
        reloc_psaut: bool = True,
) -> pd.DataFrame:
    # --- colonne base
    base_col = "fixed_commune" if "fixed_commune" in sites_alloc.columns else (
        "comune" if "comune" in sites_alloc.columns else None)
    if base_col is None:
        raise SystemExit("sites_alloc deve avere 'fixed_commune' o 'comune'.")

    sites_alloc = sites_alloc.copy()
    sites_alloc["tipo"] = sites_alloc["tipo"].astype(str).map(normalize_tipo)
    if "fixed_commune" not in sites_alloc.columns:
        sites_alloc["fixed_commune"] = sites_alloc[base_col].astype(str).map(norm_commune)
    else:
        sites_alloc["fixed_commune"] = sites_alloc["fixed_commune"].astype(str).map(norm_commune)
    if "is_fixed" not in sites_alloc.columns:
        # per compat: se manca, considera tutto come rilocabile
        sites_alloc["is_fixed"] = 0

    # --- origini OD disponibili (serve per non creare basi non raggiungibili)
    od_origins = set()
    if od_alloc is not None and not od_alloc.empty and "origin_comune" in od_alloc.columns:
        od_origins = set(od_alloc["origin_comune"].astype(str).map(norm_commune))

    # --- candidati base (ATT/POT/ALL), poi intersezione con OD
    def _read_comuni_csv(p: Path) -> List[str]:
        if p and p.exists():
            try:
                df = pd.read_csv(p)
                if "comune" in df.columns:
                    return list(df["comune"].astype(str).map(norm_commune))
            except Exception:
                pass
        return []

    bases_att = set(_read_comuni_csv(presidi_att))
    bases_pot = set(_read_comuni_csv(presidi_pot))
    all_communes = set(communes_alloc["comune"].astype(str).map(norm_commune))

    if bases_mode == "ATT":
        base_candidates = set(bases_att)
    elif bases_mode == "POT":
        base_candidates = set(bases_pot)
    elif bases_mode in ("ATT_POT", "ATT+POT"):
        base_candidates = set(bases_att) | set(bases_pot)
    elif bases_mode == "ALL":
        base_candidates = set(all_communes)
    else:
        # default prudente
        base_candidates = set(bases_att) | set(bases_pot)

    # se ho OD, tengo solo basi che esistono come origine
    if od_origins:
        base_candidates = base_candidates & od_origins
    base_candidates = sorted(base_candidates)

    # limitazione numero basi
    if limit_bases and limit_bases > 0 and len(base_candidates) > limit_bases:
        base_candidates = base_candidates[:limit_bases]

    # --- filtra tipi utili
    allowed = sites_alloc[sites_alloc["tipo"].isin(KNOWN_TYPES)].copy()

    # partizione esistenti vs acquistabili
    if "capex" in allowed.columns and "opex" in allowed.columns:
        is_existing_mask = (allowed["is_fixed"] == 1) | (
            ((allowed["capex"].fillna(0) == 0) & (allowed["opex"].fillna(0) == 0))
        )
    else:
        is_existing_mask = (allowed["is_fixed"] == 1)

    existing = allowed[is_existing_mask].copy()
    purch = allowed[~is_existing_mask].copy()

    rows: List[Dict[str, object]] = []

    # --- ESISTENTI: famiglie di riloc (1 famiglia per site_id)
    for _, r in existing.iterrows():
        sid = str(r["site_id"])
        tipo = str(r["tipo"]).upper()

        # PSAUT non rilocabili: restano fissi nella loro base
        if (tipo == "PSAUT") and (not reloc_psaut):
            rows.append({
                "site_id": sid,
                "tipo": tipo,
                "is_fixed": 1,
                "fixed_commune": r["fixed_commune"],
                "capex": float(r.get("capex", 0.0)),
                "opex": float(r.get("opex", 0.0)),
                "is_existing": 1,
                "reloc_family": "",  # niente famiglia = non rilocabile
            })
            continue

        # Altri esistenti: rilocabili su tutte le basi candidate (stessa famiglia)
        for b in base_candidates:
            rows.append({
                "site_id": f"{sid}@{b}",
                "tipo": tipo,
                "is_fixed": 0,
                "fixed_commune": b,
                "capex": 0.0,
                "opex": 0.0,
                "is_existing": 1,
                "reloc_family": sid,  # vincolo = una attiva per famiglia
            })

    # --- ACQUISTABILI
    if not purch.empty:
        tmp = purch.copy()
        if "fixed_commune" not in tmp.columns and "comune" in tmp.columns:
            tmp["fixed_commune"] = tmp["comune"].astype(str).map(norm_commune)
        tmp["is_existing"] = 0
        tmp["reloc_family"] = ""
        if "capex" not in tmp.columns: tmp["capex"] = 0.0
        if "opex" not in tmp.columns: tmp["opex"] = 0.0

        # Replichiamo SEMPRE AUTO_MED e AMB_ALS su tutte le basi candidate
        mask_rep = tmp["tipo"].astype(str).str.upper().isin(["AUTO_MED", "AMB_ALS", "CMR"])
        rep = tmp[mask_rep].copy()
        keep = tmp[~mask_rep].copy()

        # Fallback: se mancano del tutto negli input, sintetizza i template acquistabili
        if rep.empty:
            rep = pd.DataFrame([
                {"site_id": "AUTO_MED_PURCH", "tipo": "AUTO_MED", "fixed_commune": ""},
                {"site_id": "AMB_ALS_PURCH", "tipo": "AMB_ALS", "fixed_commune": ""},
                {"site_id": "CMR_PURCH", "tipo": "CMR", "fixed_commune": ""},
            ])
            rep["capex"] = 0.0
            rep["opex"] = 0.0
            rep["is_fixed"] = 0
            rep["is_existing"] = 0
            rep["reloc_family"] = ""

        for _, rr in rep.iterrows():
            sid = str(rr.get("site_id", f"{str(rr['tipo']).upper()}_PURCH"))
            tipo = str(rr["tipo"]).upper()
            for b in base_candidates:
                rows.append({
                    "site_id": f"{sid}@{b}",
                    "tipo": tipo,
                    "is_fixed": 0,
                    "fixed_commune": b,
                    "capex": float(rr.get("capex", 0.0)),
                    "opex": float(rr.get("opex", 0.0)),
                    "is_existing": 0,
                    "reloc_family": "",  # acquistabili: nessuna famiglia
                })

        # Gli altri acquistabili restano così come sono (niente replica)
        if not keep.empty:
            keep = keep[["site_id", "tipo", "is_fixed", "fixed_commune",
                         "capex", "opex", "is_existing", "reloc_family"]].copy()
            # normalizza tipi/nomi
            keep["tipo"] = keep["tipo"].astype(str).str.upper()
            keep["fixed_commune"] = keep["fixed_commune"].astype(str).map(norm_commune)
            rows.extend(keep.to_dict("records"))

    # --- DataFrame finale
    sites_reloc = pd.DataFrame(rows, columns=[
        "site_id", "tipo", "is_fixed", "fixed_commune",
        "capex", "opex", "is_existing", "reloc_family"
    ]).dropna(subset=["site_id", "tipo", "fixed_commune"])

    # normalizza
    sites_reloc["tipo"] = sites_reloc["tipo"].astype(str).map(normalize_tipo)
    sites_reloc["fixed_commune"] = sites_reloc["fixed_commune"].astype(str).map(norm_commune)
    sites_reloc["is_fixed"] = sites_reloc["is_fixed"].astype(int)
    sites_reloc["is_existing"] = sites_reloc["is_existing"].astype(int)
    if "capex" not in sites_reloc.columns: sites_reloc["capex"] = 0.0
    if "opex" not in sites_reloc.columns: sites_reloc["opex"] = 0.0

    # de-duplica eventuali duplicati
    sites_reloc = sites_reloc.drop_duplicates(subset=["site_id", "fixed_commune", "tipo"])

    return sites_reloc


# -------------------- Modello --------------------

@dataclass
class Slot:
    idx: int
    site_id: str
    tipo: str
    base: str
    is_fixed: int
    capex: float
    opex: float
    is_existing: int
    family: str
    doctors_need: float
    nurses_need: float


@dataclass
class Problem:
    communes: List[str]
    demand: np.ndarray  # (C,4)
    demand_w: np.ndarray  # (C,)
    od: np.ndarray  # (S,C)
    slots: List[Slot]
    slot_speed: np.ndarray  # (S,)
    thr_vec: np.ndarray  # (4,)
    fixed_mask: np.ndarray  # (S,)
    capex: np.ndarray
    opex: np.ndarray
    families: Dict[str, List[int]]
    feasible: np.ndarray  # (C,4)
    times: np.ndarray  # (S,C) = od * speed
    doctors_need: np.ndarray  # (S,)
    nurses_need: np.ndarray  # (S,)


def _expand_purchase_slots(purch_df, base_candidates):
    """
    Replica AUTOMATICAMENTE gli slot acquistabili su tutte le basi candidate.
    - Solo tipi utili: AUTO_MED e AMB_ALS (puoi aggiungerne altri se vuoi).
    - Nessuna famiglia di rilocazione (reloc_family=""), non sono limitati da "=1 per famiglia".
    """
    rows = []
    if purch_df is None or purch_df.empty:
        return rows

    df = purch_df.copy()

    # Normalizza colonne base
    if "tipo" not in df.columns:
        return rows
    df["tipo"] = df["tipo"].astype(str).str.upper()

    # Filtra ai soli tipi che vuoi poter "comprare dappertutto"
    df = df[df["tipo"].isin(["AUTO_MED", "AMB_ALS", "CMR"])]
    if df.empty:
        return rows

    if "capex" not in df.columns: df["capex"] = 0.0
    if "opex" not in df.columns: df["opex"] = 0.0
    if "site_id" not in df.columns:
        # id base, lo renderemo univoco aggiungendo @comune
        df["site_id"] = df["tipo"] + "_PURCH"

    for _, r in df.iterrows():
        for b in base_candidates:
            rows.append({
                "site_id": f"{r.site_id}@{b}",  # id univoco della copia per base
                "tipo": r.tipo,
                "is_fixed": 0,
                "fixed_commune": b,  # la copia è ancorata a quella base
                "capex": float(r.capex),
                "opex": float(r.opex),
                "is_existing": 0,
                "reloc_family": "",  # importantissimo: NESSUNA famiglia
            })
    return rows


def _build_times_matrix(communes_list: List[str], slots_rows: List[Dict], od_alloc: pd.DataFrame) -> Tuple[
    np.ndarray, np.ndarray]:
    C = len(communes_list)
    S = len(slots_rows)
    od_map = {(norm_commune(r["origin_comune"]), norm_commune(r["dest_comune"])): float(r["travel_time_min"])
              for _, r in od_alloc.iterrows()}
    T = np.full((S, C), 1e9, dtype=float)
    for s, sl in enumerate(slots_rows):
        o = norm_commune(sl["fixed_commune"])
        for c, name in enumerate(communes_list):
            T[s, c] = od_map.get((o, name), 1e9)
    return T, np.array([norm_commune(sl["fixed_commune"]) for sl in slots_rows], dtype=object)


def load_for_model(
        communes_alloc: pd.DataFrame,
        demand_alloc: pd.DataFrame,
        od_alloc: pd.DataFrame,
        sites_reloc: pd.DataFrame,
        type_speed: Dict[str, float],
        thresholds: Dict[str, float],
        doctors_per_type: Dict[str, float],
        nurses_per_type: Dict[str, float] = None,
        nurse_unit_opex: float = 0.0,
) -> Problem:
    nurses_per_type = nurses_per_type or {}

    # --- Comuni e domanda ---
    communes = communes_alloc["comune"].astype(str).map(norm_commune).tolist()
    cidx = {c: i for i, c in enumerate(communes)}
    C = len(communes)

    code_col = next((c for c in demand_alloc.columns if str(c).lower() in ("codice", "codice_invio", "colore", "code")),
                    None)
    val_col = next(
        (c for c in ("chiamate", "n_missioni", "n_missioni_pesate", "val", "value") if c in demand_alloc.columns), None)
    if code_col is None or val_col is None:
        raise SystemExit("demand_alloc deve avere 'comune', 'codice_invio/codice' e 'chiamate'.")

    dmd = demand_alloc.copy()
    dmd["comune"] = dmd["comune"].astype(str).map(norm_commune)
    dmd = dmd[dmd[code_col].astype(str).str.upper().isin(CODES)]
    M = np.zeros((C, 4), dtype=float)
    for _, r in dmd.iterrows():
        cm = r["comune"]
        k = str(r[code_col]).upper()
        v = float(r[val_col])
        if cm in cidx:
            M[cidx[cm], CODE_IDX[k]] += v
    W = np.array([8, 4, 2, 1], dtype=float)
    demand_w = M.dot(W)

    # --- Costruzione slot (usando le mappe per tipo passate dall'utente) ---
    slots: List[Slot] = []
    for _, r in sites_reloc.iterrows():
        t = str(r["tipo"]).upper().strip()
        if t not in KNOWN_TYPES:
            continue

        dneed = float(doctors_per_type.get(t, 0.0))
        nneed = float(nurses_per_type.get(t, 0.0))
        cap = float(r.get("capex", 0.0))
        opx = float(r.get("opex", 0.0))
        if nurse_unit_opex:
            opx += nneed * float(nurse_unit_opex)

        slots.append(Slot(
            idx=len(slots),
            site_id=str(r["site_id"]),
            tipo=t,
            base=norm_commune(r["fixed_commune"]),
            is_fixed=int(r.get("is_fixed", 0)),
            capex=cap,
            opex=opx,
            is_existing=int(r.get("is_existing", 0)),
            family=str(r.get("reloc_family", "")),
            doctors_need=dneed,
            nurses_need=nneed,
        ))
    if not slots:
        raise SystemExit("Nessuno slot valido in sites_alloc_reloc.")

    # --- OD in matrice tempi ---
    od_alloc = od_alloc.copy()
    od_alloc["origin_comune"] = od_alloc["origin_comune"].astype(str).map(norm_commune)
    od_alloc["dest_comune"] = od_alloc["dest_comune"].astype(str).map(norm_commune)
    od_map = {(r["origin_comune"], r["dest_comune"]): float(r["travel_time_min"]) for _, r in od_alloc.iterrows()}

    S = len(slots)
    T = np.full((S, C), 1e9, dtype=float)
    for i, sl in enumerate(slots):
        for c, name in enumerate(communes):
            T[i, c] = od_map.get((sl.base, name), 1e9)

    # --- Vettori/parametri del problema ---
    fixed_mask = np.array([sl.is_fixed == 1 for sl in slots], dtype=bool)
    capex = np.array([sl.capex for sl in slots], dtype=float)
    opex = np.array([sl.opex for sl in slots], dtype=float)
    slot_speed = np.array([float(type_speed.get(sl.tipo, 1.0)) for sl in slots], dtype=float)
    thr_vec = np.array([float(thresholds.get(k, d)) for k, d in zip(CODES, [8, 20, 30, 45])], dtype=float)

    times = T * slot_speed[:, None]
    doctors_need = np.array([sl.doctors_need for sl in slots], dtype=float)
    nurses_need = np.array([sl.nurses_need for sl in slots], dtype=float)

    # famiglie di rilocazione
    fam: Dict[str, List[int]] = {}
    for i, sl in enumerate(slots):
        if sl.family:
            fam.setdefault(sl.family, []).append(i)

    # raggiungibilità strutturale (feasible)
    feasible = np.zeros((C, 4), dtype=bool)
    for k in range(4):
        thr = thr_vec[k]
        best = np.min(times, axis=0) if times.size else np.full((C,), 1e9)
        feasible[:, k] = (best <= thr)

    communes_list = communes
    return Problem(
        communes=communes_list,
        demand=M,
        demand_w=demand_w,
        od=T,
        slots=slots,
        slot_speed=slot_speed,
        thr_vec=thr_vec,
        fixed_mask=fixed_mask,
        capex=capex,
        opex=opex,
        families=fam,
        feasible=feasible,
        times=times,
        doctors_need=doctors_need,
        nurses_need=nurses_need,
    )


INFEAS_PENALTY = 1e20


def coverage_stats(pb: Problem, covered_matrix: np.ndarray) -> Dict[str, float]:
    stats = {}
    tot = pb.demand.sum()
    for code, k in CODE_IDX.items():
        calls = float(pb.demand[:, k].sum())
        covered_calls = float((pb.demand[:, k] * covered_matrix[:, k]).sum())
        uncovered_calls = calls - covered_calls
        pct = (covered_calls / calls * 100.0) if calls > 0 else 100.0
        stats[f"{code}_calls"] = calls
        stats[f"{code}_covered"] = covered_calls
        stats[f"{code}_uncovered"] = uncovered_calls
        stats[f"{code}_pct"] = pct
    stats["total_calls"] = float(tot)
    stats["total_uncovered"] = float(np.sum(pb.demand * (~covered_matrix)))
    stats["total_pct"] = 100.0 * (1.0 - stats["total_uncovered"] / stats["total_calls"]) if stats[
                                                                                                "total_calls"] > 0 else 100.0
    return stats


# -------------------- Solver CP-SAT --------------------

from ortools.sat.python import cp_model


def solve_mip(
        pb: Problem,
        doctor_codes_req: List[bool],
        doctor_cover_mode: str,
        psaut_min: int,
        psaut_exact: Optional[int],
        full_mode: str = "strict",
        threads: int = 8,
        time_limit_sec: Optional[float] = None,
        verbose: bool = True,
        doctors_total: Optional[float] = None,
        doctors_budget_mode: str = "absolute",  # (per compatibilità, qui gestiamo solo 'absolute')
        relax_weights: Optional[Dict[str, float]] = None,
        budget_total: Optional[float] = None,
        budget_mode: str = "purchase",
        objective: str = "max_cover_budget",
        lambda_cost: float = 1.0,
        turnoff_doctor_families: bool = False,
        nurses_total: Optional[float] = None,  # NUOVO
        auto_med_transport: str = "off",  # NUOVO
        auto_transport_delay: float = 5.0,  # <— NUOVO
):
    model = cp_model.CpModel()
    S = len(pb.slots)
    C = len(pb.communes)
    K = 4

    relax_weights = dict(relax_weights or {})
    relax_weights.setdefault("COV", int(1e9))
    relax_weights.setdefault("DOC", int(8e8))
    relax_weights.setdefault("PSAUT", int(8e8))
    relax_weights.setdefault("DOCTORS", int(8e8))
    relax_weights.setdefault("NURSES", int(8e8))
    relax_weights.setdefault("BUDGET", int(8e8))

    # x[i]: attivazione slot (fissi forzati a 1)
    x: List[cp_model.IntVar] = []
    for i, sl in enumerate(pb.slots):
        xi = model.NewIntVar(1, 1, f"x_{i}") if sl.is_fixed else model.NewIntVar(0, 1, f"x_{i}")
        x.append(xi)

    # famiglie di rilocazione
    # famiglie di rilocazione
    for fam_id, idxs in pb.families.items():
        if not idxs:
            continue
        is_doc_family = any(pb.doctors_need[i] > 0 for i in idxs)
        if turnoff_doctor_families and is_doc_family:
            for i in idxs:
                model.Add(x[i] == 0)  # spegni famiglia medica
            continue
        # Con budget medici finito: la famiglia medica può anche NON essere attivata
        if is_doc_family and (doctors_total is not None):
            model.Add(sum(x[i] for i in idxs) <= 1)
        else:
            model.Add(sum(x[i] for i in idxs) == 1)

    # Coupling AUTO_MED ↔ AMBULANZA (comportamento esistente: base/global)
    if auto_med_transport in ("base", "global"):
        def is_auto(i: int) -> bool:
            return pb.slots[i].tipo == "AUTO_MED"

        def is_amb(i: int) -> bool:
            return pb.slots[i].tipo in ("AMB_ALS", "AMB_ILS")

        if auto_med_transport == "base":
            by_base: Dict[str, List[int]] = {}
            for i, sl in enumerate(pb.slots):
                by_base.setdefault(sl.base, []).append(i)
            for base, idxs in by_base.items():
                A = [i for i in idxs if is_auto(i)]
                B = [i for i in idxs if is_amb(i)]
                if A and B:
                    model.Add(sum(x[i] for i in A) <= sum(x[i] for i in B))
        else:
            A = [i for i in range(S) if is_auto(i)]
            B = [i for i in range(S) if is_amb(i)]
            if A and B:
                model.Add(sum(x[i] for i in A) <= sum(x[i] for i in B))

    # PSAUT min/exact (con slack)
    psaut_idx = [i for i, sl in enumerate(pb.slots) if sl.tipo == "PSAUT"]
    if psaut_min is not None and psaut_min > 0:
        slack_under = model.NewIntVar(0, S, "psaut_under_min")
        model.Add(sum(x[i] for i in psaut_idx) + slack_under >= int(psaut_min))
    if psaut_exact is not None:
        psaut_sum = sum(x[i] for i in psaut_idx)
        slack_under = model.NewIntVar(0, S, "psaut_exact_under")
        slack_over = model.NewIntVar(0, S, "psaut_exact_over")
        model.Add(psaut_sum + slack_under >= int(psaut_exact))
        model.Add(psaut_sum - slack_over <= int(psaut_exact))

    # Budget medici/infermieri
    # Medici HARD
    d_over = None  # << inizializzato per evitare NameError più avanti
    if doctors_total is not None:
        SCALE = 1000
        coeff = [int(round(float(pb.doctors_need[i]) * SCALE)) for i in range(S)]
        expr = sum(coeff[i] * x[i] for i in range(S))
        limit = int(round(float(doctors_total) * SCALE))
        model.Add(expr <= limit)  # vincolo duro

    # Infermieri (soft con slack, come da tuo codice)
    n_over = None
    if nurses_total is not None:
        SCALE = 1000
        coeff = [int(round(float(pb.nurses_need[i]) * SCALE)) for i in range(S)]
        expr = sum(coeff[i] * x[i] for i in range(S))
        limit = int(round(float(nurses_total) * SCALE))
        n_over = model.NewIntVar(0, 10 ** 9, "nurses_overrun")
        model.Add(expr <= limit + n_over)

    # Budget costi
    b_over = None
    if budget_total is not None:
        SCALE = 1000
        if budget_mode == "purchase":
            coeff_cost = []
            for i in range(S):
                purch = (not pb.slots[i].is_fixed)
                cost = (pb.capex[i] + pb.opex[i]) if purch else 0.0
                coeff_cost.append(int(round(cost * SCALE)))
        else:
            coeff_cost = [int(round((pb.capex[i] + pb.opex[i]) * SCALE)) for i in range(S)]
        expr = sum(coeff_cost[i] * x[i] for i in range(S))
        limit = int(round(float(budget_total) * SCALE))

        model.Add(expr <= limit)

    # Copertura (ANY + DOC)
    thr = [float(t) for t in pb.thr_vec]  # [R,G,V,B]
    cover_ik = [[[] for _ in range(K)] for __ in range(C)]
    cover_doc_ik = [[[] for _ in range(K)] for __ in range(C)]
    code_list = CODES
    doc_codes = {code_list[i] for i, need in enumerate(doctor_codes_req) if need}

    for i in range(S):
        for c in range(C):
            t_min = pb.times[i, c]
            for k in range(K):
                if t_min <= thr[k]:
                    cover_ik[c][k].append(i)
                    if pb.doctors_need[i] > 0:
                        cover_doc_ik[c][k].append(i)

    y_any = [[model.NewBoolVar(f"y_any_c{c}_k{k}") for k in range(K)] for c in range(C)]
    y_doc = [[model.NewBoolVar(f"y_doc_c{c}_k{k}") for k in range(K)] for c in range(C)]

    for c in range(C):
        for k in range(K):
            Sck = cover_ik[c][k]
            if Sck:
                model.Add(sum(x[i] for i in Sck) >= y_any[c][k])
            else:
                model.Add(y_any[c][k] == 0)

    if doctor_cover_mode in ("strict", "feasible-only"):
        for c in range(C):
            for k in range(K):
                code_name = code_list[k]
                if code_name in doc_codes:
                    Sdck = cover_doc_ik[c][k]
                    if Sdck:
                        model.Add(sum(x[i] for i in Sdck) >= y_doc[c][k])
                        if doctor_cover_mode == "strict":
                            model.Add(y_any[c][k] <= y_doc[c][k])
                    else:
                        model.Add(y_doc[c][k] == 0)
                        if doctor_cover_mode == "strict":
                            model.Add(y_any[c][k] == 0)
                else:
                    model.Add(y_doc[c][k] == 0)
    else:
        for c in range(C):
            for k in range(K):
                model.Add(y_doc[c][k] == 0)

    # ====== Regola di TRASPORTO: AUTO_MED richiede ILS entro T[k] + Δ ======
    # Attiva solo se dall'index è selezionato "vincolo globale" (auto_med_transport == "global").
    # ====== Regola di TRASPORTO: AUTO_MED richiede AMB (ILS o ALS) entro T[k] + Δ
    # Attiva solo se "auto_med_transport == 'global'".
    if auto_med_transport == "global":
        for c in range(C):
            for k in range(K):
                thr_with_delay = thr[k] + float(auto_transport_delay)
                # AUTO_MED attive che arrivano entro T[k] (per c)
                A = [i for i in range(S)
                     if pb.slots[i].tipo == "AUTO_MED" and pb.times[i, c] <= thr[k]]
                # Mezzi di TRASPORTO validi: ILS **o** ALS entro T[k]+Δ
                L = [i for i in range(S)
                     if pb.slots[i].tipo in ("AMB_ILS", "AMB_ALS")
                     and pb.times[i, c] <= thr_with_delay]

                # b_auto = 1 se c'è almeno una AUTO_MED ATTIVA (tra quelle in A)
                if A:
                    M_A = len(A)
                    sA = sum(x[i] for i in A)
                    b_auto = model.NewBoolVar(f"b_auto_c{c}_k{k}")
                    model.Add(sA >= b_auto)
                    model.Add(sA <= M_A * b_auto)
                else:
                    b_auto = None

                # b_amb = 1 se c'è almeno una AMB (ILS o ALS) ATTIVA (tra quelle in L)
                if L:
                    M_L = len(L)
                    sL = sum(x[i] for i in L)
                    b_amb = model.NewBoolVar(f"b_amb_c{c}_k{k}")
                    model.Add(sL >= b_amb)
                    model.Add(sL <= M_L * b_amb)
                else:
                    b_amb = None

                # Se c'è automedica attiva per (c,k), deve esserci anche almeno una AMB (ILS/ALS)
                if b_auto is not None:
                    if b_amb is not None:
                        one_minus_auto = model.NewIntVar(0, 1, f"one_minus_auto_c{c}_k{k}")
                        model.Add(one_minus_auto == 1 - b_auto)
                        # b_amb >= b_auto  <=>  b_amb + (1 - b_auto) >= 1
                        model.Add(b_amb + one_minus_auto >= 1)
                    else:
                        # Nessun mezzo valido entro T[k]+Δ -> vieta lo "y_any=1 con AUTO_MED"
                        model.Add(b_auto == 0)

    # Obiettivo
    SCALE = 1000
    benefit_terms = []
    for c in range(C):
        for k in range(K):
            w = int(round(float(pb.demand[c, k]) * SCALE))
            if w > 0:
                benefit_terms.append(w * y_any[c][k])

    cost_terms = []
    for i in range(S):
        cost = pb.capex[i] + pb.opex[i]
        if budget_mode == "purchase" and pb.slots[i].is_fixed:
            cost = 0.0
        cost_terms.append(int(round(lambda_cost * cost * SCALE)) * x[i])

    pen_terms = []
    if d_over is not None:
        pen_terms.append(int(relax_weights["DOCTORS"]) * d_over)
    if n_over is not None:
        pen_terms.append(int(relax_weights["NURSES"]) * n_over)
    if b_over is not None:
        pen_terms.append(int(relax_weights["BUDGET"]) * b_over)
    for name in ("psaut_under_min", "psaut_exact_under", "psaut_exact_over"):
        try:
            v = model.GetVarFromProtoName(name)
            pen_terms.append(int(relax_weights["PSAUT"]) * v)
        except Exception:
            pass

    model.Maximize(sum(benefit_terms) - sum(cost_terms) - sum(pen_terms))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = int(threads or 8)
    if time_limit_sec:
        solver.parameters.max_time_in_seconds = float(time_limit_sec)
    if not verbose:
        solver.parameters.log_search_progress = False

    result = solver.Solve(model)
    ok = result in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    # Costruisci soluzione
    bits = np.zeros((S,), dtype=int)
    if ok:
        for i in range(S):
            bits[i] = int(solver.Value(x[i]))

    # KPI + covered_matrix
    active_idx = np.where(bits == 1)[0]
    purchase_cost = float(np.sum(pb.capex[active_idx] * (1 - pb.fixed_mask[active_idx])))
    opex_cost = float(np.sum(pb.opex[active_idx]))
    total_cost = purchase_cost + opex_cost

    doctors_used = float(np.sum(pb.doctors_need[active_idx]))
    nurses_used = float(np.sum(pb.nurses_need[active_idx]))

    covered_matrix = np.zeros((C, K), dtype=bool)
    for c in range(C):
        for k in range(K):
            covered_matrix[c, k] = bool(ok and solver.Value(y_any[c][k]) == 1)

    uncov = float(np.sum(pb.demand * (~covered_matrix)))

    best = {
        "bits": bits,
        "purchase_cost": purchase_cost,
        "opex_cost": opex_cost,
        "total_cost": total_cost,
        "doctors_used": doctors_used,
        "nurses_used": nurses_used,
        "covered_matrix": covered_matrix,
        "uncov": uncov,
        "status": str(result),
    }
    info = {"objective": float(solver.ObjectiveValue()) if ok else None,
            "runtime_sec": float(solver.WallTime())}
    return best, info


def evaluate_plan(
        data_dir: Path,
        out_dir: Path,
        thresholds_map: Dict[str, float],
        type_speed: Dict[str, float],
        purchase_costs: Dict[str, float],
        opex_costs: Dict[str, float],
        bases: str,
        limit_bases: int,
        full_coverage: str,
        doctors_per_type: Dict[str, float],
        doctor_codes_req,
        doctor_cover_mode: str,
        psaut_min: int,
        psaut_exact: Optional[int],
        reloc_psaut: bool,
        plan: List[Dict],
        # --- nuovi argomenti opzionali, retro-compatibili ---
        nurses_per_type: Optional[Dict[str, float]] = None,
        nurse_unit_opex: Optional[float] = None,
        nurses_total: Optional[float] = None,
):
    """
    Valuta un 'piano' (senza ottimizzazione) attivando slot coerenti col piano.
    Il piano è una lista di dict: {"base_comune": str, "tipo": str, "qty": int, "source": "purchase|existing|any"}.
    Genera gli stessi CSV di un run (chosen_slots.csv, coverage_summary.csv, ecc.) dentro out_dir.
    Ritorna un piccolo dizionario con KPI e confronto baseline.
    """

    # 1) Carica input e costruisci famiglie/slot come in run_single_case
    communes = load_communes(data_dir)
    sites = load_or_build_sites(data_dir)
    od = load_od_any(data_dir, sites)
    demand = load_demand(data_dir)

    presidi_att = data_dir / "presidi_attuali.csv"
    presidi_pot = data_dir / "presidi_potenziali.csv"
    sites_reloc = build_reloc_families(
        sites, communes, presidi_att, presidi_pot, od,
        bases_mode=bases, limit_bases=limit_bases, reloc_psaut=reloc_psaut
    )

    # Applica costi (per gli acquistabili)
    if "capex" not in sites_reloc.columns:
        sites_reloc["capex"] = 0.0
    if "opex" not in sites_reloc.columns:
        sites_reloc["opex"] = 0.0
    mask_purch = (sites_reloc["is_existing"].fillna(0) == 0)
    sites_reloc.loc[mask_purch, "capex"] = sites_reloc.loc[mask_purch, "tipo"].map(
        lambda t: purchase_costs.get(t, 0.0)).astype(float)
    sites_reloc.loc[mask_purch, "opex"] = sites_reloc.loc[mask_purch, "tipo"].map(
        lambda t: opex_costs.get(t, 0.0)).astype(float)

    # --- INFERMIERI: normalizza input ---
    def _normalize_nurses_map(x):
        if not x:
            return {}
        if isinstance(x, dict):
            # normalizza chiavi stile "AMB-ALS" -> "AMB_ALS"
            return {
                str(k).upper().replace("-", "_").replace(" ", "_"): float(v)
                for k, v in x.items()
                if v is not None
            }
        if isinstance(x, str):
            mp = {}
            for chunk in x.split(","):
                if "=" in chunk:
                    k, v = chunk.split("=", 1)
                    k = k.strip().upper().replace("-", "_").replace(" ", "_")
                    try:
                        mp[k] = float(v)
                    except Exception:
                        pass
            return mp
        return {}

    nurses_per_type = _normalize_nurses_map(nurses_per_type)

    # --- INFERMIERI: normalizza (può arrivare come "PSAUT=6,AUTO_MED=0,AMB_ALS=1,AMB_ILS=1") ---
    def _norm_nurses_map(x):
        if not x:
            return {}
        if isinstance(x, dict):
            return {str(k).upper().replace('-', '_').replace(' ', '_'): float(v) for k, v in x.items() if v is not None}
        if isinstance(x, str):
            mp = {}
            for chunk in x.split(','):
                if '=' in chunk:
                    k, v = chunk.split('=', 1)
                    k = k.strip().upper().replace('-', '_').replace(' ', '_')
                    try:
                        mp[k] = float(v)
                    except Exception:
                        pass
            return mp
        return {}

    nurses_per_type = _norm_nurses_map(nurses_per_type)
    pb = load_for_model(
        communes, demand, od, sites_reloc, type_speed, thresholds_map,
        doctors_per_type,
        nurses_per_type=nurses_per_type,
        nurse_unit_opex=float(nurse_unit_opex or 0.0),
    )

    # 2) Costruisci i bits a partire dal piano
    S = len(pb.slots)
    bits = np.zeros((S,), dtype=np.int8)  # NB: fixed saranno aggiunti via pb.fixed_mask dentro evaluate()

    # Helper: attiva N slot per (tipo, base) rispettando "source"
    def activate(tipo: str, base: str, qty: int, source: str) -> int:
        t = str(tipo).upper().replace("-", "_").replace(" ", "_")
        b = norm_commune(base)
        n = int(max(0, qty or 0))
        if n == 0:
            return 0

        chosen = 0

        # candidate sets
        purch_idxs = [i for i, sl in enumerate(pb.slots)
                      if (sl.tipo == t and sl.base == b and sl.is_existing == 0 and not pb.fixed_mask[i])]
        # per gli esistenti rilocabili scegli una (e una sola) clone per famiglia
        fam_best = []
        for fam_id, idxs in pb.families.items():
            # gli slot di famiglia hanno tutti stesso tipo; prendi la clone sulla base richiesta
            for i in idxs:
                sl = pb.slots[i]
                if sl.tipo == t and sl.base == b:
                    fam_best.append(i)
                    break  # 1 clone per famiglia

        exist_idxs = [i for i in fam_best if not pb.fixed_mask[i]]

        if source == "purchase":
            cand = purch_idxs
        elif source == "existing":
            cand = exist_idxs
        else:  # "any"
            cand = exist_idxs + purch_idxs

        for i in cand:
            if chosen >= n:
                break
            bits[i] = 1
            chosen += 1
        return chosen

    # Normalizza il piano
    plan = plan or []
    activated = 0
    for row in plan:
        base = row.get("base_comune") or row.get("base") or row.get("comune") or ""
        tipo = row.get("tipo") or ""
        qty = row.get("qty") or row.get("quantita") or row.get("n") or 1
        src = (row.get("source") or "any").strip().lower()
        if src not in ("purchase", "existing", "any"):
            src = "any"
        activated += activate(tipo, base, qty, src)

    # 3) Valuta: copertura/costi su piano e baseline
    fitness, uncov, extra = evaluate(pb, bits, full_mode=full_coverage)
    best = {"bits": bits, "uncov": uncov, **extra}

    # baseline (solo fissi)
    bits_zero = np.zeros_like(bits)
    _, uncov_base, extra_base = evaluate(pb, bits_zero, full_mode=full_coverage)

    # 4) Esporta CSV come un run normale → la dashboard li sa già leggere
    out_dir.mkdir(parents=True, exist_ok=True)
    export_results(pb, best, out_dir)  # chosen_slots.csv, coverage_summary.csv, doctor_coverage_summary.csv, ecc.

    # KPI riassuntivi (ANY e DOC)
    any_stats = coverage_stats(pb, best["covered_matrix"])
    # copertura con medico per KPI aggregato (riuso della logica di run_single_case)
    active = np.logical_or(pb.fixed_mask, best["bits"]).astype(bool)
    doc_rows = np.where(np.array([s.doctors_need > 0 for s in pb.slots], dtype=bool) & active)[0]
    if doc_rows.size > 0:
        best_doc = np.min(pb.times[doc_rows, :], axis=0)
    else:
        best_doc = np.full((len(pb.communes),), 1e9)
    doctor_covered = np.zeros((len(pb.communes), 4), dtype=bool)
    for code, k in CODE_IDX.items():
        thr = pb.thr_vec[k]
        doctor_covered[:, k] = (best_doc <= thr)
    doc_stats = coverage_stats(pb, doctor_covered)

    # Conta quante unità sono "nuove" (acquisti) fra gli attivi
    new_count = 0
    for i, sl in enumerate(pb.slots):
        if np.logical_or(pb.fixed_mask, best["bits"])[i] and (sl.is_existing == 0) and (not sl.is_fixed):
            new_count += 1

    # fissi ∪ selezionati
    _active_mask = np.logical_or(pb.fixed_mask, best["bits"])

    # === RUN SUMMARY per la UI (evita 404 su run_summary.csv) ===
    try:
        _active_mask = np.logical_or(pb.fixed_mask, best["bits"]).astype(bool)
        _doctors_used = float(np.sum(pb.doctors_need[np.where(_active_mask)[0]]))
        _nurses_used = float(np.sum(pb.nurses_need[np.where(_active_mask)[0]])) if hasattr(pb, "nurses_need") else 0.0

        metrics = {
            "any_pct": any_stats.get("total_pct", None),
            "doc_pct": doc_stats.get("total_pct", None),
            "purchase_cost": best["purchase_cost"],
            "opex_cost": best["opex_cost"],
            "total_cost": best["total_cost"],
            "doctors_used": _doctors_used,
            "nurses_used": _nurses_used,
            # se hai passato nurses_total a evaluate_plan lo riproponiamo (altrimenti vuoto)
            "nurses_total": nurses_total if nurses_total is not None else ""
        }
        pd.DataFrame([metrics]).to_csv(out_dir / "run_summary.csv", index=False)
    except Exception:
        pass

    # KPI infermieri (se supportati dal modello)
    try:
        nurses_used = float(np.sum(pb.nurses_need[np.where(_active_mask)[0]]))
    except Exception:
        nurses_used = 0.0

    return {
        "purchase_cost": best["purchase_cost"],
        "opex_cost": best["opex_cost"],
        "total_cost": best["total_cost"],
        "doctors_used": float(np.sum(pb.doctors_need[np.where(_active_mask)[0]])),
        "nurses_used": nurses_used,
        "any_pct": any_stats.get("total_pct", None),
        "doc_pct": doc_stats.get("total_pct", None),
        "baseline_any_pct": None if extra_base is None else coverage_stats(
            pb, np.zeros_like(best["covered_matrix"], dtype=bool)
        ).get("total_pct", None),
        "baseline_uncov": uncov_base,
        "activated_units": int(activated),
        "new_units": int(new_count)
    }


def evaluate(pb: Problem, bits_full: np.ndarray, full_mode: str = "strict"):
    C = len(pb.communes)
    active = np.logical_or(pb.fixed_mask, bits_full)
    purchase_cost = float(np.sum(pb.capex[np.logical_and(active, ~pb.fixed_mask) & (pb.capex > 0)]))
    opex_cost = float(np.sum(pb.opex[np.logical_and(active, ~pb.fixed_mask) & (pb.opex > 0)]))
    total_cost = purchase_cost + opex_cost

    adj = pb.times[active, :]
    best = np.min(adj, axis=0) if adj.size else np.full((C,), 1e9)
    covered = np.zeros((C, 4), dtype=bool)
    for k, thr in enumerate(pb.thr_vec):
        covered[:, k] = (best <= thr)

    uncovered = np.where(covered, 0.0, pb.demand)

    if full_mode != "off":
        req = (pb.demand > 0)
        if full_mode == "feasible-only":
            req = req & pb.feasible
        must_cover = np.where(req, pb.demand, 0.0)
        missing = float(np.sum(must_cover * (~covered)))
        if missing > 0:
            fitness = INFEAS_PENALTY + missing
            return fitness, float(np.sum(uncovered)), {
                "purchase_cost": purchase_cost,
                "opex_cost": opex_cost,
                "total_cost": total_cost,
                "covered_matrix": covered,
            }
    fitness = total_cost


    return fitness, float(np.sum(uncovered)), {
        "purchase_cost": purchase_cost,
        "opex_cost": opex_cost,
        "total_cost": total_cost,
        "covered_matrix": covered,
    }



# -------------------- Export --------------------

def export_results(pb: Problem, best, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    active = np.logical_or(pb.fixed_mask, best["bits"]).astype(bool)

    # doctors + nurses summary
    doctors_used = float(np.sum(pb.doctors_need[np.where(active)[0]]))
    nurses_used = float(np.sum(pb.nurses_need[np.where(active)[0]]))
    with open(out_dir / "doctors_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Doctors required by active slots = {doctors_used:.2f}\n"
                f"Nurses required by active slots  = {nurses_used:.2f}\n")

    rows = []
    for i, sl in enumerate(pb.slots):
        if active[i]:
            rows.append({
                "slot_idx": i,
                "site_id": sl.site_id,
                "tipo": sl.tipo,
                "base_comune": sl.base,
                "is_fixed": sl.is_fixed,
                "is_existing": sl.is_existing,
                "reloc_family": sl.family,
                "purchase_cost": 0.0 if (sl.is_fixed or sl.is_existing) else sl.capex,
                "opex_cost": 0.0 if (sl.is_fixed or sl.is_existing) else sl.opex,
                "doctors_need": sl.doctors_need,
                "nurses_need": sl.nurses_need,
            })
    pd.DataFrame(rows).to_csv(out_dir / "chosen_slots.csv", index=False)

    covered = best["covered_matrix"]
    demand = pb.demand
    communes = pb.communes

    # Dettaglio "ANY"
    det = []
    for c_idx, cm in enumerate(communes):
        for code, k in CODE_IDX.items():
            calls = demand[c_idx, k]
            if calls > 0:
                det.append({
                    "comune": cm,
                    "codice": code,
                    "chiamate": calls,
                    "covered": bool(covered[c_idx, k]),
                    "uncovered": 0.0 if covered[c_idx, k] else float(calls),
                })
    df = pd.DataFrame(det)
    df.to_csv(out_dir / "uncovered_by_comune_code.csv", index=False)
    if not df.empty:
        summ = df.groupby("codice")[["chiamate", "uncovered"]].sum().reset_index()
        summ["covered"] = summ["chiamate"] - summ["uncovered"]
        summ.loc["TOTAL"] = ["TOTAL", summ["chiamate"].sum(), summ["uncovered"].sum(), summ["covered"].sum()]
        summ.to_csv(out_dir / "coverage_summary.csv", index=False)

    # Dettaglio "DOCTOR"
    doctor_rows = np.where(np.array([s.doctors_need > 0 for s in pb.slots], dtype=bool) & active)[0]
    if doctor_rows.size > 0:
        doctor_times = pb.times[doctor_rows, :]
        best_doc = np.min(doctor_times, axis=0)
    else:
        best_doc = np.full((len(pb.communes),), 1e9)
    doctor_covered = np.zeros((len(pb.communes), 4), dtype=bool)
    for code, k in CODE_IDX.items():
        thr = pb.thr_vec[k]
        doctor_covered[:, k] = (best_doc <= thr)

    det_doc = []
    for c_idx, cm in enumerate(communes):
        for code, k in CODE_IDX.items():
            calls = demand[c_idx, k]
            if calls > 0:
                det_doc.append({
                    "comune": cm,
                    "codice": code,
                    "chiamate": calls,
                    "doctor_covered": bool(doctor_covered[c_idx, k]),
                    "uncovered_doctor": 0.0 if doctor_covered[c_idx, k] else float(calls),
                })
    df_doc = pd.DataFrame(det_doc)
    df_doc.to_csv(out_dir / "doctor_uncovered_by_comune_code.csv", index=False)
    if not df_doc.empty:
        summ_doc = df_doc.groupby("codice")[["chiamate", "uncovered_doctor"]].sum().reset_index()
        summ_doc["doctor_covered"] = summ_doc["chiamate"] - summ_doc["uncovered_doctor"]
        summ_doc.loc["TOTAL"] = ["TOTAL", summ_doc["chiamate"].sum(), summ_doc["uncovered_doctor"].sum(),
                                 summ_doc["doctor_covered"].sum()]
        summ_doc.to_csv(out_dir / "doctor_coverage_summary.csv", index=False)

    # (comune,codice) con domanda >0 ma mai raggiungibili sotto soglia (ANY)
    impossible = []
    for c_idx, cm in enumerate(communes):
        for code, k in CODE_IDX.items():
            if demand[c_idx, k] > 0 and (not pb.feasible[c_idx, k]):
                impossible.append({"comune": cm, "codice": code, "chiamate": float(demand[c_idx, k])})
    if impossible:
        pd.DataFrame(impossible).to_csv(out_dir / "structurally_impossible.csv", index=False)

    # Report di fattibilità (minimo, basato sugli overrun se presenti)
    relax = {
        "doctors_overrun_staff": 0.0,
        "nurses_overrun_staff": 0.0,
        "budget_overrun_cost": 0.0,
        "cov_pct": coverage_stats(pb, covered).get("total_pct", 100.0),
        "doc_pct": coverage_stats(pb, doctor_covered).get("total_pct", 100.0),
        "cov_total": int((pb.demand > 0).sum()),
        "cov_viol": int((pb.demand * (~covered) > 0).sum())
    }
    with open(out_dir / "feasibility_report.txt", "w", encoding="utf-8") as f:
        f.write("=== FEASIBILITY REPORT ===\n")
        f.write(f"Coverage ANY ≈ {relax['cov_pct']:.2f}%\n")
        f.write(f"Coverage DOC ≈ {relax['doc_pct']:.2f}%\n")

    pd.DataFrame([relax]).to_csv(out_dir / "feasibility_summary.csv", index=False)


# -------------------- Run singolo caso --------------------

def run_single_case(
        data_dir: Path,
        out_dir: Path,
        thresholds_map: Dict[str, float],
        type_speed: Dict[str, float],
        purchase_costs: Dict[str, float],
        opex_costs: Dict[str, float],
        bases: str,
        limit_bases: int,
        full_coverage: str,
        threads: int,
        time_limit_sec: Optional[float],
        verbose: bool,
        doctors_total: Optional[float],
        doctors_per_type: Dict[str, float],
        doctors_budget_mode: str,
        doctor_codes_req: List[bool],
        doctor_cover_mode: str,
        psaut_min: int,
        psaut_exact: Optional[int],
        relax_weights: Dict[str, float],
        reloc_psaut: bool,
        budget_total: Optional[float] = None,
        turnoff_doctor_families_mode: str = "auto",
        budget_mode: str = "purchase",
        objective: str = "max_cover_budget",
        lambda_cost: float = 1.0,
        # NUOVI:
        nurses_total: Optional[float] = None,
        nurses_per_type: Optional[Dict[str, float]] = None,
        nurse_unit_opex: float = 0.0,
        auto_med_transport: str = "off",
        auto_transport_delay: float = 5.0,
):
    communes = load_communes(data_dir)
    sites = load_or_build_sites(data_dir)
    od = load_od_any(data_dir, sites)
    demand = load_demand(data_dir)

    presidi_att = data_dir / "presidi_attuali.csv"
    presidi_pot = data_dir / "presidi_potenziali.csv"
    sites_reloc = build_reloc_families(
        sites, communes, presidi_att, presidi_pot, od,
        bases_mode=bases, limit_bases=limit_bases, reloc_psaut=reloc_psaut
    )

    if "capex" not in sites_reloc.columns:
        sites_reloc["capex"] = 0.0
    if "opex" not in sites_reloc.columns:
        sites_reloc["opex"] = 0.0
    mask_purch = (sites_reloc["is_existing"].fillna(0) == 0)

    purch_types = set(sites_reloc.loc[mask_purch, "tipo"].astype(str).str.upper().unique())
    missing_cap = sorted([t for t in purch_types if t not in purchase_costs])
    missing_op = sorted([t for t in purch_types if t not in opex_costs])
    if missing_cap or missing_op:
        raise SystemExit(
            "Mancano costi per tipi acquistabili: "
            f"CAPEX→{missing_cap or '-'}  OPEX→{missing_op or '-'}.\n"
            "Passali con --purchase-costs e --opex-costs (es. ..., PSAUT=XXX)."
        )

    sites_reloc.loc[mask_purch, "capex"] = sites_reloc.loc[mask_purch, "tipo"].map(
        lambda t: purchase_costs.get(t, 0.0)).astype(float)
    sites_reloc.loc[mask_purch, "opex"] = sites_reloc.loc[mask_purch, "tipo"].map(
        lambda t: opex_costs.get(t, 0.0)).astype(float)

    all_types = set(sites_reloc["tipo"].astype(str).str.upper().unique())
    missing_speed = sorted([t for t in all_types if t not in type_speed])
    if missing_speed and verbose:
        print("[WARN] Manca type-speed per:", ", ".join(missing_speed), "(uso 1.0)")

    # nurses_per_type default
    nurses_per_type = nurses_per_type or {}

    pb = load_for_model(communes, demand, od, sites_reloc, type_speed, thresholds_map,
                        doctors_per_type, nurses_per_type, nurse_unit_opex=nurse_unit_opex)

    # -------------------- AUTO turnoff famiglie con medico --------------------
    def _auto_turnoff_doctor_families(pb) -> bool:
        if doctors_total is None:
            return False  # medici illimitati -> non spegnere

        staff_psaut = float(doctors_per_type.get("PSAUT", 0.0))

        fixed_doc = float(np.sum(pb.doctors_need[np.where(pb.fixed_mask)[0]]))

        fixed_psaut_count = sum(1 for s in pb.slots if s.tipo == "PSAUT" and s.is_fixed == 1)
        current_psaut_doc = fixed_psaut_count * staff_psaut

        target_psaut = psaut_exact if psaut_exact is not None else max(psaut_min or 0, fixed_psaut_count)
        add_psaut_doc_needed = max(0.0, target_psaut * staff_psaut - current_psaut_doc)

        floor_docs = fixed_doc + add_psaut_doc_needed
        spare = doctors_total - floor_docs

        doc_family_needs = []
        for idxs in pb.families.values():
            if any(pb.doctors_need[i] > 0 for i in idxs):
                doc_family_needs.append(float(pb.doctors_need[idxs[0]]))
        min_need = min(doc_family_needs) if doc_family_needs else float("inf")

        return (spare < (min_need - 1e-9))

    if turnoff_doctor_families_mode == "on":
        _turnoff_bool = True
    elif turnoff_doctor_families_mode == "off":
        _turnoff_bool = False
    else:
        _turnoff_bool = _auto_turnoff_doctor_families(pb)

    t0 = time.time()
    best, _ = solve_mip(
        pb,
        doctor_codes_req=doctor_codes_req,
        doctor_cover_mode=doctor_cover_mode,
        psaut_min=psaut_min,
        psaut_exact=psaut_exact,
        full_mode=full_coverage,
        threads=threads,
        time_limit_sec=time_limit_sec,
        verbose=verbose,
        doctors_total=doctors_total,
        doctors_budget_mode=doctors_budget_mode,
        relax_weights=relax_weights,
        budget_total=budget_total,
        budget_mode=budget_mode,
        objective=objective,
        lambda_cost=lambda_cost,
        turnoff_doctor_families=_turnoff_bool,
        nurses_total=nurses_total,
        auto_transport_delay=auto_transport_delay,
        auto_med_transport=auto_med_transport,
    )
    dt = time.time() - t0

    export_results(pb, best, out_dir)

    stats_any = coverage_stats(pb, best["covered_matrix"])

    # Doctor coverage stats (ricompute rapido)
    active = np.logical_or(pb.fixed_mask, best["bits"]).astype(bool)
    doc_rows = np.where(np.array([s.doctors_need > 0 for s in pb.slots], dtype=bool) & active)[0]
    if doc_rows.size > 0:
        doctor_times = pb.times[doc_rows, :]
        best_doc = np.min(doctor_times, axis=0)
    else:
        best_doc = np.full((len(pb.communes),), 1e9)
    doctor_covered = np.zeros((len(pb.communes), 4), dtype=bool)
    for code, k in CODE_IDX.items():
        thr = pb.thr_vec[k]
        doctor_covered[:, k] = (best_doc <= thr)
    stats_doc = coverage_stats(pb, doctor_covered)

    relax = {}
    doc_line = ""
    if doctors_total is not None:
        doc_line = f" | Doctors used≈{best.get('doctors_used', 0.0):.2f} / {doctors_total:.2f}"
    nur_line = ""
    if nurses_total is not None:
        nur_line = f" | Nurses used≈{best.get('nurses_used', 0.0):.2f} / {nurses_total:.2f}"
    print(
        f"[OK] MIP finito in {dt:,.1f}s. Uncovered={best['uncov']:.2f}  Cost={best['total_cost']:.0f}{doc_line}{nur_line} | ANY≈{stats_any.get('total_pct', 0.0):.1f}%")

    return {
        "elapsed_sec": dt,
        "purchase_cost": best["purchase_cost"],
        "opex_cost": best["opex_cost"],
        "total_cost": best["total_cost"],
        "doctors_used": best.get("doctors_used", 0.0),
        "nurses_used": best.get("nurses_used", 0.0),
        **{f"ANY_{k}": v for k, v in stats_any.items()},
        **{f"DOC_{k}": v for k, v in stats_doc.items()},
        **{f"RELAX_{k}": v for k, v in relax.items()},
    }


# -------------------- MAIN --------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--T", default="ROSSO=8,GIALLO=20,VERDE=30,BIANCO=45")
    ap.add_argument("--type-speed",
                    default="AUTO_MED=0.90,AMB_ALS=0.98,AMB_ILS=1.00,CMR=0.95")
    ap.add_argument("--purchase-costs",
                    default="AUTO_MED=500000,AMB_ALS=350000,AMB_ILS=250000,CMR=450000")
    ap.add_argument("--opex-costs",
                    default="AUTO_MED=250000,AMB_ALS=200000,AMB_ILS=150000,CMR=220000")
    ap.add_argument("--bases", choices=["ATT_POT", "ALL"], default="ATT_POT")
    ap.add_argument("--limit-bases", type=int, default=0)
    ap.add_argument("--full-coverage", choices=["off", "strict", "feasible-only"], default="strict")
    ap.add_argument("--threads", type=int, default=8, help="Numero di thread CP-SAT")
    ap.add_argument("--time-limit-sec", type=float, default=None, help="Time limit (sec) opzionale")
    ap.add_argument("--verbose", action="store_true")

    # Medici / Staff 24/7
    ap.add_argument("--doctors-total", type=float, default=None,
                    help="Budget totale medici (unità staff 24/7). Se omesso: illimitato.")
    ap.add_argument("--doctors-per-type", default="", help="[DEPRECATO] Usa --staff-per-type (compatibilità).")
    ap.add_argument("--staff-per-type", default="",
                    help="Mappa tipo→n. medici per slot 24/7 (es. PSAUT=6,AUTO_MED=3,AMB_ALS=3).")
    ap.add_argument("--doctors-budget-mode", choices=["absolute", "incremental"], default="absolute",
                    help="Vincolo medici: absolute = su tutti gli slot attivi; incremental = solo sugli acquistabili (compatibilità).")

    # Ruolo medico & PSAUT
    ap.add_argument("--doctor-codes", default="",
                    help="Codici che richiedono copertura con medico (es. 'ROSSO,GIALLO'). Vuoto=off.")
    ap.add_argument("--doctor-cover", choices=["off", "strict", "feasible-only"], default="off",
                    help="Vincolo copertura con medico per i codici indicati.")
    ap.add_argument("--psaut-min", type=int, default=0, help="Numero minimo di presidi PSAUT attivi.")
    ap.add_argument("--psaut-exact", type=int, default=None, help="Totale esatto di PSAUT attivi (inclusi i fissi).")
    ap.add_argument("--reloc-psaut", choices=["on", "off"], default="off",
                    help="Se 'off', i PSAUT esistenti non sono rilocabili e restano fissi nella base iniziale (default).")

    ap.add_argument("--auto-transport-delay", type=float, default=5.0,
                    help="Minuti extra concessi all’AMB_ILS rispetto a T[k] per validare copertura con AUTO_MED")

    # Analisi multi-caso
    ap.add_argument("--cases-csv", default=None,
                    help=("CSV con i casi (colonne opzionali: label, doctors_total, staff_per_type, "
                          "doctors_per_type, nurses_total, nurses_per_type, nurse_unit_opex, auto_med_transport, "
                          "doctors_budget_mode, reloc_psaut, doctor_codes, doctor_cover, psaut_min, psaut_exact, "
                          "T, type_speed, purchase_costs, opex_costs, bases, limit_bases, full_coverage, "
                          "time_limit_sec, relax_weights, budget_total, budget_mode, objective, lambda_cost)"))
    ap.add_argument("--sweep-doctors-total", default=None,
                    help="Lista di valori per il budget medici: es. '0,8,12,16'.")

    # Pesi relax
    ap.add_argument("--relax-weights", default="",
                    help="Pesi per le violazioni (mappa tipo→peso). Chiavi: COV,DOC,PSAUT,DOCTORS,NURSES,BUDGET.")

    # Budget totale (costi) e modalità
    ap.add_argument("--budget-total", type=float, default=None,
                    help="Budget massimo (CAPEX+OPEX) per gli slot attivi (dipende da --budget-mode). Se omesso: illimitato.")

    ap.add_argument("--budget-mode", choices=["purchase", "all"], default="purchase",
                    help="Ambito budget: purchase=solo acquistabili; all=tutti gli slot attivi.")

    # Infermieri / staff 24/7
    ap.add_argument("--nurses-total", type=float, default=None,
                    help="Budget totale infermieri (FTE 24/7). Se omesso: illimitato.")
    ap.add_argument("--nurses-per-type", default="",
                    help="Mappa tipo→FTE infermieri per unità 24/7 (es. PSAUT=1,AUTO_MED=1,AMB_ALS=2,AMB_ILS=2).")
    ap.add_argument("--nurse-unit-opex", type=float, default=0.0,
                    help="Costo annuo per FTE infermiere; viene sommato all’OPEX dello slot in base ai FTE richiesti.")

    # Coupling AutoMed ↔ Ambulanza (trasporto)
    ap.add_argument("--auto-med-transport", choices=["off", "base", "global"], default="off",
                    help="Se 'base': per ogni base #AUTO_MED ≤ #AMB(ALS+ILS). Se 'global': vincolo a livello di sistema.")

    # Obiettivo di ottimizzazione
    ap.add_argument("--objective", choices=["min_cost", "max_cover_budget"], default="max_cover_budget",
                    help="min_cost: minimizza i costi a parità di copertura; max_cover_budget: massimizza la copertura soggetta al budget (default).")
    ap.add_argument("--lambda-cost", type=float, default=1.0,
                    help="Peso (lambda) del costo nell'obiettivo max_cover_budget (penalità soft).")
    ap.add_argument(
        "--turnoff-doctor-families",
        choices=["auto", "on", "off"],
        default="auto",
        help="auto: spegne famiglie con medico se i medici disponibili non bastano; on: sempre; off: mai."
    )

    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    thresholds_map = parse_map(args.T, cast=float)
    type_speed = parse_map(args.type_speed, cast=float)
    purchase_costs = parse_map(args.purchase_costs, cast=float)
    opex_costs = parse_map(args.opex_costs, cast=float)

    # Staff per slot 24/7 (default PSAUT=6, altri esempio 3)
    staff_per_type = parse_map(args.staff_per_type, cast=float)
    if not staff_per_type:
        legacy = parse_map(args.doctors_per_type, cast=float)
        staff_per_type = legacy if legacy else {"AUTO_MED": 3.0, "AMB_ALS": 3.0, "PSAUT": 6.0}

    nurses_per_type = parse_map(args.nurses_per_type, cast=float)

    doctor_codes_req = parse_doctor_codes(args.doctor_codes)
    relax_weights = parse_weights(args.relax_weights)

    # ----- Modalità multi-caso: CSV -----
    if args.cases_csv:
        cases_df = pd.read_csv(args.cases_csv)
        rows = []
        for i, r in cases_df.iterrows():
            lbl = str(r.get("label", f"case_{i + 1}")).strip()
            label_s = re.sub(r"[^A-Za-z0-9_\-]+", "_", lbl)[:40] or f"case_{i + 1}"
            case_dir = out_dir / f"case_{i + 1:03d}_{label_s}"

            T_case = parse_map(r.get("T", None), cast=float) or thresholds_map
            ts_case = parse_map(r.get("type_speed", None), cast=float) or type_speed
            cap_case = parse_map(r.get("purchase_costs", None), cast=float) or purchase_costs
            opx_case = parse_map(r.get("opex_costs", None), cast=float) or opex_costs
            bases_case = str(r.get("bases", args.bases)) if pd.notna(r.get("bases", None)) else args.bases
            lb_case = int(r.get("limit_bases", args.limit_bases)) if pd.notna(
                r.get("limit_bases", None)) else args.limit_bases
            full_case = str(r.get("full_coverage", args.full_coverage)) if pd.notna(
                r.get("full_coverage", None)) else args.full_coverage
            tl_case = float(r.get("time_limit_sec", args.time_limit_sec)) if pd.notna(
                r.get("time_limit_sec", None)) else args.time_limit_sec
            docs_total_case = float(r.get("doctors_total")) if pd.notna(
                r.get("doctors_total", np.nan)) else args.doctors_total
            staff_case = parse_map(r.get("staff_per_type", None), cast=float) or \
                         parse_map(r.get("doctors_per_type", None), cast=float) or \
                         staff_per_type
            doc_codes_case = parse_doctor_codes(r.get("doctor_codes", "")) if pd.notna(
                r.get("doctor_codes", None)) else doctor_codes_req
            doc_cover_case = str(r.get("doctor_cover", args.doctor_cover)) if pd.notna(
                r.get("doctor_cover", None)) else args.doctor_cover
            psaut_min_case = int(r.get("psaut_min", args.psaut_min)) if pd.notna(
                r.get("psaut_min", None)) else args.psaut_min
            psaut_exact_case = int(r.get("psaut_exact", args.psaut_exact)) if pd.notna(
                r.get("psaut_exact", None)) else args.psaut_exact
            relax_w_case = parse_weights(r.get("relax_weights", "")) if pd.notna(
                r.get("relax_weights", None)) else relax_weights
            docs_mode_case = str(r.get("doctors_budget_mode", args.doctors_budget_mode)) if pd.notna(
                r.get("doctors_budget_mode", None)) else args.doctors_budget_mode
            reloc_psaut_case = str(r.get("reloc_psaut", args.reloc_psaut)) if pd.notna(
                r.get("reloc_psaut", None)) else args.reloc_psaut
            reloc_flag = (str(reloc_psaut_case).lower() == "on")

            nurses_total_case = float(r.get("nurses_total")) if pd.notna(
                r.get("nurses_total", np.nan)) else args.nurses_total
            nurses_per_case = parse_map(r.get("nurses_per_type", None), cast=float) or nurses_per_type
            nurse_unit_opex_case = float(r.get("nurse_unit_opex")) if pd.notna(
                r.get("nurse_unit_opex", np.nan)) else args.nurse_unit_opex
            auto_med_transport_case = str(r.get("auto_med_transport", args.auto_med_transport)) if pd.notna(
                r.get("auto_med_transport", None)) else args.auto_med_transport

            budget_total_case = float(r.get("budget_total")) if pd.notna(
                r.get("budget_total", np.nan)) else args.budget_total
            budget_mode_case = str(r.get("budget_mode", args.budget_mode)) if pd.notna(
                r.get("budget_mode", None)) else args.budget_mode

            print(f"=== CASE {i + 1} — {lbl} ===")
            metrics = run_single_case(
                data_dir=data_dir,
                out_dir=case_dir,
                thresholds_map=T_case,
                type_speed=ts_case,
                purchase_costs=cap_case,
                opex_costs=opx_case,
                bases=bases_case,
                limit_bases=lb_case,
                full_coverage=full_case,
                threads=args.threads,
                time_limit_sec=tl_case,
                verbose=True,
                doctors_total=docs_total_case,
                doctors_per_type=staff_case,
                doctors_budget_mode=docs_mode_case,
                doctor_codes_req=doc_codes_case,
                doctor_cover_mode=doc_cover_case,
                psaut_min=psaut_min_case,
                psaut_exact=psaut_exact_case,
                relax_weights=relax_w_case,
                reloc_psaut=reloc_flag,
                budget_total=budget_total_case,
                budget_mode=budget_mode_case,
                objective=args.objective,
                lambda_cost=args.lambda_cost,
                turnoff_doctor_families_mode=args.turnoff_doctor_families,
                nurses_total=nurses_total_case,
                auto_transport_delay=args.auto_transport_delay,
                nurses_per_type=nurses_per_case,
                nurse_unit_opex=nurse_unit_opex_case,
                auto_med_transport=auto_med_transport_case,
            )
            rows.append({"idx": i + 1, "label": lbl, "out_dir": str(case_dir),
                         "doctors_total": docs_total_case, "nurses_total": nurses_total_case, **metrics})
        pd.DataFrame(rows).to_csv(out_dir / "cases_summary.csv", index=False)
        print("\n[OK] Analisi multi-caso completata. Tabella: cases_summary.csv")
        return

    # ----- Modalità sweep dei medici -----
    sweep_docs = parse_list_nums(args.sweep_doctors_total, cast=float)
    if sweep_docs:
        rows = []
        for j, D in enumerate(sweep_docs):
            lbl = f"DOCS_{int(D) if float(D).is_integer() else D}"
            case_dir = out_dir / f"case_{j + 1:03d}_{lbl}"
            print(f"\n=== CASE {j + 1} — {lbl} ===")
            metrics = run_single_case(
                data_dir=data_dir,
                out_dir=case_dir,
                thresholds_map=thresholds_map,
                type_speed=type_speed,
                purchase_costs=purchase_costs,
                opex_costs=opex_costs,
                bases=args.bases,
                limit_bases=args.limit_bases,
                full_coverage=args.full_coverage,
                threads=args.threads,
                time_limit_sec=args.time_limit_sec,
                verbose=True,
                doctors_total=float(D),
                doctors_per_type=staff_per_type,
                doctors_budget_mode=args.doctors_budget_mode,
                doctor_codes_req=doctor_codes_req,
                doctor_cover_mode=args.doctor_cover,
                psaut_min=args.psaut_min,
                psaut_exact=args.psaut_exact,
                relax_weights=relax_weights,
                reloc_psaut=(args.reloc_psaut == "on"),
                budget_total=args.budget_total,
                budget_mode=args.budget_mode,
                objective=args.objective,
                lambda_cost=args.lambda_cost,
                turnoff_doctor_families_mode=args.turnoff_doctor_families,
                nurses_total=args.nurses_total,
                nurses_per_type=nurses_per_type,
                nurse_unit_opex=args.nurse_unit_opex,
                auto_med_transport=args.auto_med_transport,
                auto_transport_delay=args.auto_transport_delay,
            )
            rows.append({"idx": j + 1, "label": lbl, "out_dir": str(case_dir),
                         "doctors_total": float(D), "nurses_total": args.nurses_total, **metrics})
        pd.DataFrame(rows).to_csv(out_dir / "cases_summary.csv", index=False)
        print("\n[OK] Analisi sweep completata. Tabella: cases_summary.csv")
        return

    # ----- Singolo caso -----
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = run_single_case(
        data_dir=data_dir,
        out_dir=out_dir,
        thresholds_map=thresholds_map,
        type_speed=type_speed,
        purchase_costs=purchase_costs,
        opex_costs=opex_costs,
        bases=args.bases,
        limit_bases=args.limit_bases,
        full_coverage=args.full_coverage,
        threads=args.threads,
        time_limit_sec=args.time_limit_sec,
        verbose=args.verbose,
        doctors_total=args.doctors_total,
        doctors_per_type=staff_per_type,
        doctors_budget_mode=args.doctors_budget_mode,
        doctor_codes_req=doctor_codes_req,
        doctor_cover_mode=args.doctor_cover,
        psaut_min=args.psaut_min,
        psaut_exact=args.psaut_exact,
        relax_weights=relax_weights,
        reloc_psaut=(args.reloc_psaut == "on"),
        budget_total=args.budget_total,
        budget_mode=args.budget_mode,
        objective=args.objective,
        lambda_cost=args.lambda_cost,
        turnoff_doctor_families_mode=args.turnoff_doctor_families,
        nurses_total=args.nurses_total,
        auto_transport_delay=args.auto_transport_delay,
        nurses_per_type=nurses_per_type,
        nurse_unit_opex=args.nurse_unit_opex,
        auto_med_transport=args.auto_med_transport,
    )
    pd.DataFrame([metrics]).to_csv(out_dir / "run_summary.csv", index=False)


if __name__ == "__main__":
    main()
