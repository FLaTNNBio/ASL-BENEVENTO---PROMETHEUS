from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .stratification_service import get_stratification_geography

# ============================================================
# CONFIGURAZIONE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

AMBULANZE_DATA_DIR = (
        PROJECT_ROOT
        / "Ambulanze-main"
        / "AmbulanzeASL"
        / "dataset"
        / "data"
)

DEFAULT_OUTPUT_DIR = (
        PROJECT_ROOT
        / "outputs"
        / "118_scenarios"
)

ALLOWED_METRICS = {
    "patient_count",
    "mean_baseline_need",
}

DEFAULT_TIER_SHARES = {
    "ALTA": 0.25,
    "MEDIA": 0.45,
    "BASSA": 0.30,
}

# Pesi originali Ambulanze 118.
DEFAULT_TIER_WEIGHTS = {
    "ALTA": 1.30,
    "MEDIA": 1.10,
    "BASSA": 1.00,
}


# ============================================================
# ERRORI
# ============================================================

class PH118SeverityError(RuntimeError):
    """Errore controllato nella costruzione della severità PH → 118."""


# ============================================================
# UTILITY NOMI COMUNE
# ============================================================

def normalize_comune(value: Any) -> str:
    """
    Normalizzazione leggera del nome del comune.
    viene usata solamente per effettuare join robusti.
    """
    if value is None:
        return ""

    text = str(value).strip()
    text = (text.replace("’", "'").replace("`", "'"))
    text = re.sub(r"\s+", " ", text, )
    return text.casefold()


def _find_column(df: pd.DataFrame, candidates: Iterable[str], ) -> Optional[str]:
    lower_map = {str(col).strip().lower(): col
                 for col in df.columns
                 }

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None


# ============================================================
# ESTRAZIONE RISULTATI GEOGRAFICI POPULATION HEALTH
# ============================================================

def _extract_geography_rows(payload: Any, ) -> List[Dict[str, Any]]:
    """
    Supporta più forme di risposta del service geografico
    così da non accoppiare troppo questo modulo
    all'implementazione HTTP.
    """

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise PH118SeverityError("Formato geography Population Health non riconosciuto.")

    for key in ("municipalities", "rows", "data", "results",):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    raise PH118SeverityError("La risposta geography non contiene una lista di comuni.")


def load_population_health_geography(run_id: str, ) -> pd.DataFrame:
    if not run_id:
        raise PH118SeverityError("run_id Population Health mancante.")

    payload = get_stratification_geography(run_id=run_id)
    rows = _extract_geography_rows(payload)

    if not rows:
        raise PH118SeverityError(f"Nessun dato geografico trovato per il run {run_id}.")

    df = pd.DataFrame(rows)
    comune_col = _find_column(df, ("municipality", "residence_municipality", "comune",), )

    if comune_col is None:
        raise PH118SeverityError("Nei dati Population Health manca il comune.")

    if "patient_count" not in df.columns:
        raise PH118SeverityError("Nei dati geografici manca patient_count.")

    if "mean_baseline_need" not in df.columns:
        raise PH118SeverityError("Nei dati geografici manca mean_baseline_need.")

    out = pd.DataFrame(
        {
            "comune": (df[comune_col].astype(str).str.strip()),
            "patient_count": pd.to_numeric(df["patient_count"], errors="coerce", ).fillna(0),
            "mean_baseline_need": pd.to_numeric(df["mean_baseline_need"], errors="coerce", ),
        }
    )

    out["_comune_key"] = (out["comune"].map(normalize_comune))
    out = out[out["_comune_key"] != ""].copy()

    # --------------------------------------------------------
    # Protezione per eventuali alias/duplicati.
    #
    # patient_count viene sommato.
    # mean_baseline_need viene mediato pesando sul numero di pazienti.
    # --------------------------------------------------------

    grouped_rows = []
    for comune_key, group in out.groupby("_comune_key", sort=True, ):

        patient_count = float(group["patient_count"].sum())
        valid_need = group[group["mean_baseline_need"].notna()]
        if not valid_need.empty and valid_need["patient_count"].sum() > 0:
            weighted_need = ((valid_need["mean_baseline_need"] * valid_need["patient_count"]).sum() / valid_need[
                "patient_count"].sum())

        elif not valid_need.empty:
            weighted_need = float(valid_need["mean_baseline_need"].mean())

        else:
            weighted_need = None

        grouped_rows.append(
            {
                "comune": group.iloc[0]["comune"],
                "_comune_key": comune_key,
                "patient_count": patient_count,
                "mean_baseline_need": weighted_need,
            }
        )

    result = pd.DataFrame(grouped_rows)
    return result


# ============================================================
# POPOLAZIONE RESIDENTE
# ============================================================

POPULATION_COLUMN_CANDIDATES = (
    "popolazione",
    "population",
    "residenti",
    "abitanti",
    "pop",
    "popolazione_residente",
    "resident_population",
    "tot_residenti",
)


def _candidate_population_files() -> List[Path]:
    return [
        AMBULANZE_DATA_DIR / "population_by_comune.csv",
        AMBULANZE_DATA_DIR / "comuni.csv",
        AMBULANZE_DATA_DIR / "comuni_geocoded.csv",
    ]


def load_resident_population(population_csv: Optional[Path] = None, ) -> pd.DataFrame:
    """
    Cerca automaticamente una colonna popolazione
    nei file comunali del progetto Ambulanze.
    Se non esiste, viene restituito un errore esplicito.
    """

    candidates = []

    if population_csv is not None: candidates.append(Path(population_csv))
    candidates.extend(_candidate_population_files())
    checked = []

    for path in candidates:
        path = Path(path)
        if not path.exists():
            continue
        checked.append(str(path))
        df = pd.read_csv(path)

        comune_col = _find_column(df, ("comune", "municipality", "denominazione", "nome_comune",), )
        population_col = _find_column(df, POPULATION_COLUMN_CANDIDATES, )

        if comune_col is None or population_col is None:
            continue

        out = pd.DataFrame(
            {
                "comune": (df[comune_col].astype(str).str.strip()),
                "resident_population": pd.to_numeric(df[population_col], errors="coerce", ),
            }
        )

        out = out[out["resident_population"] > 0].copy()
        out["_comune_key"] = (out["comune"].map(normalize_comune))
        out = (out.drop_duplicates("_comune_key").reset_index(drop=True))

        if not out.empty:
            return out

    raise PH118SeverityError(
        "Non è stata trovata una colonna con la "
        "popolazione residente nei file comunali. "
        "File controllati: "
        + ", ".join(checked)
    )


# ============================================================
# INDICATORE PH
# ============================================================

def build_metric_dataframe(geography_df: pd.DataFrame, metric: str,
                           population_csv: Optional[Path] = None, ) -> pd.DataFrame:
    if metric not in ALLOWED_METRICS:
        raise PH118SeverityError(
            f"Indicatore non supportato: {metric}. "
            f"Ammessi: {sorted(ALLOWED_METRICS)}"
        )

    df = geography_df.copy()
    if metric == "mean_baseline_need":
        df["ph_raw_value"] = pd.to_numeric(df["mean_baseline_need"], errors="coerce", )
        df["ph_value"] = (df["ph_raw_value"])
        df["metric_unit"] = "baseline_need_mean"
        df["resident_population"] = pd.NA

    elif metric == "patient_count":

        population_df = load_resident_population(population_csv)

        df = df.merge(population_df[["_comune_key", "resident_population", ]], on="_comune_key", how="left",
                      validate="one_to_one", )

        missing_population = df[df["resident_population"].isna()]["comune"].tolist()

        if missing_population:
            raise PH118SeverityError(
                "Popolazione residente mancante per "
                f"{len(missing_population)} comuni: "
                + ", ".join(
                    missing_population[:10]
                )
            )

        df["ph_raw_value"] = pd.to_numeric(df["patient_count"], errors="coerce", ).fillna(0)

        # Pazienti Population Health ogni 1000 residenti.
        df["ph_value"] = (df["ph_raw_value"] / df["resident_population"] * 1000.0)

        df["metric_unit"] = "patients_per_1000_residents"

    if df["ph_value"].isna().all():
        raise PH118SeverityError(f"L'indicatore {metric} non contiene valori validi.")
    return df


# ============================================================
# ASSEGNAZIONE TIER
# ============================================================

def assign_severity_tiers(metric_df: pd.DataFrame, tier_shares: Optional[Dict[str, float]] = None,
                          tier_weights: Optional[Dict[str, float]] = None, ) -> pd.DataFrame:
    """
    Sostituisce l'assegnazione casuale originale dei tier
    con una classificazione deterministica guidata dal
    valore Population Health.

    Vengono mantenuti:
    - 25% ALTA
    - 45% MEDIA
    - 30% BASSA

    e i pesi:
    - ALTA 1.30
    - MEDIA 1.10
    - BASSA 1.00
    """

    shares = dict(tier_shares or DEFAULT_TIER_SHARES)
    weights = dict(tier_weights or DEFAULT_TIER_WEIGHTS)
    share_sum = sum(shares.values())

    if abs(share_sum - 1.0) > 1e-6:
        raise PH118SeverityError("Le quote ALTA/MEDIA/BASSA devono sommare a 1.")

    df = metric_df.copy()

    # in caso di valore identico utilizziamo il nome comune.
    df = df.sort_values(["ph_value", "_comune_key", ], ascending=[False, True, ], na_position="last", ).reset_index(
        drop=True)
    n = len(df)
    if n == 0:
        raise PH118SeverityError("Nessun comune disponibile per assegnare la severità.")

    high_end = shares["ALTA"]
    medium_end = shares["ALTA"] + shares["MEDIA"]
    tiers = []
    for index in range(n):
        # Percentile ordinato dal valore più alto.
        percentile = (index / n)
        if percentile < high_end:
            tier = "ALTA"
        elif percentile < medium_end:
            tier = "MEDIA"
        else:
            tier = "BASSA"

        tiers.append(tier)

    df["severity_tier"] = tiers
    df["tier_weight"] = (df["severity_tier"].map(weights).astype(float))

    return df


# ============================================================
# DOMANDA 118 ORIGINALE
# ============================================================

def load_original_118_demand() -> pd.DataFrame:
    path = (AMBULANZE_DATA_DIR/ "demand_by_comune_code.csv")

    if not path.exists():
        raise PH118SeverityError(f"File domanda 118 non trovato: {path}")

    df = pd.read_csv(path)
    required = {"comune", "codice", "n_missioni",}

    missing = (required - set(df.columns))

    if missing:
        raise PH118SeverityError(
            "demand_by_comune_code.csv non contiene le colonne: "
            + ", ".join(sorted(missing))
        )

    out = df[["comune", "codice", "n_missioni", ]].copy()

    out["codice"] = (out["codice"].astype(str).str.upper().str.strip())
    out["n_missioni"] = pd.to_numeric(out["n_missioni"], errors="coerce",).fillna(0)
    out["_comune_key"] = (out["comune"].map(normalize_comune))

    return out

# ============================================================
# PREVIEW
# ============================================================

def preview_ph_118_severity(run_id: str, metric: str,population_csv: Optional[Path] = None,) -> Dict[str, Any]:
    """
    Costruisce la preview.
    IMPORTANTE:
    non scrive file e non modifica il dataset 118.
    """

    geography_df = (load_population_health_geography(run_id))
    metric_df = ( build_metric_dataframe( geography_df, metric, population_csv,))
    severity_df = (assign_severity_tiers(metric_df))
    demand_df = (load_original_118_demand())

    severity_cols = [
        "_comune_key",
        "ph_raw_value",
        "ph_value",
        "metric_unit",
        "severity_tier",
        "tier_weight",
        "resident_population",
    ]

    weighted = demand_df.merge(severity_df[severity_cols], on="_comune_key", how="left", validate="many_to_one", )

    missing = (weighted["tier_weight"].isna())
    missing_communes = sorted(weighted.loc[missing, "comune", ].dropna().unique().tolist())

    if missing_communes:
        raise PH118SeverityError(
            "Mancata corrispondenza Population Health per alcuni comuni 118: "+ ", ".join(missing_communes[:10])
        )

    # --------------------------------------------------------
    # NON viene modificatp:
    # codice
    # n_missioni
    #
    # Creiamo solo la domanda pesata.
    # --------------------------------------------------------

    weighted["n_missioni_pesate"] = (weighted["n_missioni"] * weighted["tier_weight"]).round(2)
    weighted["severity_source"] = "population_health"
    weighted["ph_run_id"] = run_id
    weighted["ph_metric"] = metric

    tier_counts = (severity_df["severity_tier"].value_counts().to_dict())
    municipalities = []
    for _, row in severity_df.iterrows():
        municipalities.append(
            {
                "comune": row["comune"],
                "patient_count": float(row["patient_count"]),
                "mean_baseline_need": (
                    None
                    if pd.isna(row["mean_baseline_need"])
                    else float(row["mean_baseline_need"])),
                "resident_population": (
                    None
                    if pd.isna(row["resident_population"])
                    else float(row["resident_population"])),
                "ph_value": float(row["ph_value"]),
                "severity_tier": row["severity_tier"],
                "tier_weight": float(row["tier_weight"]),
            }
        )

    return {
        "run_id": run_id,
        "metric": metric,
        "severity_source": ("population_health"),
        "tier_shares": dict(DEFAULT_TIER_SHARES),
        "tier_weights": dict(DEFAULT_TIER_WEIGHTS),
        "tier_counts": tier_counts,
        "municipality_count": len(severity_df),
        "municipalities": municipalities,
        "_weighted_dataframe": weighted,
        "_severity_dataframe": severity_df,
    }


# ============================================================
# CONFERMA / CREAZIONE SCENARIO
# ============================================================

def materialize_ph_118_scenario(preview: Dict[str, Any], output_root: Optional[Path] = None, ) -> Dict[str, Any]:
    """
    Da chiamare SOLTANTO dopo la conferma dell'utente.
    Scrive uno scenario separato.Non sovrascrive mai dataset/data.
    """

    run_id = str(preview["run_id"])
    metric = str(preview["metric"])
    weighted = preview.get("_weighted_dataframe")
    severity = preview.get("_severity_dataframe")

    if not isinstance( weighted, pd.DataFrame, ):
        raise PH118SeverityError("Preview priva del weighted dataframe.")

    if not isinstance(severity, pd.DataFrame,):
        raise PH118SeverityError("Preview priva del severity dataframe.")

    root = Path(output_root or DEFAULT_OUTPUT_DIR)
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id, )
    scenario_id = (f"ph_{safe_run_id}_{metric}")
    scenario_dir = ( root / scenario_id)
    scenario_dir.mkdir(parents=True, exist_ok=True,)

    weighted_path = (scenario_dir / "weighted_demand_by_comune_code.csv")
    severity_path = (scenario_dir / "severity_by_comune.csv")
    metadata_path = (scenario_dir / "severity_metadata.json")
    weighted_out = weighted[
        [
            "comune",
            "codice",
            "n_missioni",
            "severity_source",
            "ph_run_id",
            "ph_metric",
            "ph_raw_value",
            "ph_value",
            "metric_unit",
            "resident_population",
            "severity_tier",
            "tier_weight",
            "n_missioni_pesate",
        ]
    ].copy()

    weighted_out.to_csv(weighted_path, index=False, encoding="utf-8-sig", )
    severity_out = severity[
        [
            "comune",
            "patient_count",
            "mean_baseline_need",
            "resident_population",
            "ph_raw_value",
            "ph_value",
            "metric_unit",
            "severity_tier",
            "tier_weight",
        ]
    ].copy()

    severity_out.to_csv(severity_path, index=False, encoding="utf-8-sig", )

    metadata = {
        "scenario_id": scenario_id,
        "created_at": (datetime.now().astimezone().isoformat()),
        "severity_source": ("population_health"),
        "source_run_id": run_id,
        "metric": metric,
        "method": "population_health_territorial_weighting",
        "patient_count_normalization": (
            "patients_per_1000_residents"
            if metric == "patient_count"
            else None
        ),
        "tier_assignment": ( "deterministic_rank"),
        "tier_shares": dict(DEFAULT_TIER_SHARES),
        "tier_weights": dict(DEFAULT_TIER_WEIGHTS),
        "municipality_count": int(len(severity)),
        "tier_counts": severity["severity_tier"].value_counts().to_dict(),
        "original_demand_modified": False,
        "emergency_codes_modified": False,
        "files": {
            "weighted_demand": str(weighted_path),
            "severity_by_comune": str(severity_path),
        },
    }

    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, ), encoding="utf-8",)

    return {
        "scenario_id": scenario_id,
        "scenario_dir": str(scenario_dir),
        "weighted_demand_path": str(weighted_path),
        "severity_path": str(severity_path),
        "metadata_path": str(metadata_path),
        "metadata": metadata,
    }
