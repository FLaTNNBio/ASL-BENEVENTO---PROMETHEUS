# -*- coding: utf-8 -*-
"""
simulate_demand_and_severity.py

Genera dataset sintetici (plausibili) a partire da comuni.csv:
- demand_by_comune_code.csv
- severita_comuni.csv
- weighted_demand_by_comune_code.csv
- thresholds_by_comune.csv

Parametri principali:
--comuni-csv   path al CSV con colonna 'comune'
--out-dir      cartella di output
--seed         seme per riproducibilità (default 118)
--total-missions  totale missioni complessive su tutti i comuni (default 20000)
--mix-high / --mix-med / --mix-low   mix per codici (ROSSO,GIALLO,VERDE,BIANCO) in ALTA/MEDIA/BASSA
--tier-shares   quota comuni per tier (es. "ALTA=0.25,MEDIA=0.45,BASSA=0.30")
--tier-weights  pesi per domanda (ALTA=1.3,MEDIA=1.1,BASSA=1.0)
--lea-base      soglie base min per codici (es. "ROSSO=8,GIALLO=20,VERDE=30,BIANCO=45")
--lea-delta     delta minuti per tier (es. "ALTA=-2,MEDIA=-1,BASSA=0")
"""

import argparse, os, math, re
import numpy as np
import pandas as pd

CODES = ["ROSSO","GIALLO","VERDE","BIANCO"]
DEFAULT_WEIGHTS = {"ROSSO":8,"GIALLO":4,"VERDE":2,"BIANCO":1}

def parse_kv(s, keys=None, cast=float):
    if not s: return {}
    out={}
    for part in s.split(","):
        if "=" not in part: continue
        k,v = part.split("=",1)
        k=k.strip().upper()
        v=v.strip()
        try:
            out[k] = cast(v)
        except Exception:
            pass
    if keys:
        # riempie le chiavi mancanti con 0
        for k in keys:
            out.setdefault(k, 0 if cast!=str else "")
    return out

def norm_commune(x):
    x = str(x).strip().replace("’","'")
    x = re.sub(r"\s+"," ",x)
    return " ".join(w.capitalize() if "'" not in w else (w[0].upper()+w[1:]) for w in x.split())

def clamp_probs(p):
    # evita zeri netti, rinormalizza
    p = np.array(p, dtype=float)
    p[p<1e-9]=1e-9
    p = p / p.sum()
    return p

def main(args):
    rng = np.random.default_rng(args.seed)

    # --- carica comuni
    dfc = pd.read_csv(args.comuni_csv)
    if "comune" not in dfc.columns:
        raise SystemExit("Il file comuni deve avere la colonna 'comune'.")
    comuni = dfc["comune"].map(norm_commune).dropna().unique().tolist()
    n = len(comuni)
    if n==0:
        raise SystemExit("Nessun comune trovato in comuni.csv")

    os.makedirs(args.out_dir, exist_ok=True)

    # --- share dei tier
    tier_shares = parse_kv(args.tier_shares, keys=["ALTA","MEDIA","BASSA"], cast=float)
    if not tier_shares:
        tier_shares = {"ALTA":0.25,"MEDIA":0.45,"BASSA":0.30}
    # genera assegnazione tier per comuni
    tiers = np.random.default_rng(args.seed+1).choice(
        ["ALTA","MEDIA","BASSA"],
        size=n,
        p=clamp_probs([tier_shares["ALTA"], tier_shares["MEDIA"], tier_shares["BASSA"]])
    )
    df_tier = pd.DataFrame({"comune": comuni, "severity_tier": tiers})

    # --- volume totale per comune: distribuzione a coda lunga (Gamma), poi scala al totale richiesto
    shape, scale = 2.0, 1.0
    vol = rng.gamma(shape, scale, size=n)
    vol = vol / vol.sum()
    vol = vol * max(args.total_missions, n)  # assicura almeno 1 a testa quando arrotondiamo
    # minimo per comune (es. 5) per evitare zeri e campioni microscopici
    vol = np.maximum(vol, 5.0)
    # ricala per rispettare esattamente il totale richiesto
    vol = vol * (args.total_missions / vol.sum())
    n_tot_comune = np.rint(vol).astype(int)
    # aggiusta scarto dovuto all'arrotondamento
    diff = args.total_missions - int(n_tot_comune.sum())
    if diff != 0:
        # distribuisci diff sui comuni più grandi (se positivo) o più piccoli (se negativo)
        order = np.argsort((-n_tot_comune) if diff>0 else (n_tot_comune))
        for i in order[:abs(diff)]:
            n_tot_comune[i] += 1 if diff>0 else -1

    # --- mix per codice in base al tier
    mix_hi = [float(x) for x in (args.mix_high or "0.25,0.40,0.30,0.05").split(",")]
    mix_md = [float(x) for x in (args.mix_med  or "0.15,0.35,0.40,0.10").split(",")]
    mix_lo = [float(x) for x in (args.mix_low  or "0.08,0.25,0.50,0.17").split(",")]
    mix_hi, mix_md, mix_lo = clamp_probs(mix_hi), clamp_probs(mix_md), clamp_probs(mix_lo)

    tier_to_mix = {"ALTA":mix_hi, "MEDIA":mix_md, "BASSA":mix_lo}

    # --- genera conteggi per codice per ciascun comune (multinomiali)
    rows = []
    for cm, tr, nt in zip(comuni, tiers, n_tot_comune):
        probs = tier_to_mix[tr]
        if nt <= 0:
            counts = np.array([0,0,0,0], dtype=int)
        else:
            counts = rng.multinomial(int(nt), probs)
        for code, c in zip(CODES, counts):
            rows.append({"comune": cm, "codice": code, "n_missioni": int(c)})

    df_demand = pd.DataFrame(rows)
    # rimuovi eventuali righe con zero (opzionale; se preferisci tenerle, commenta la riga sotto)
    df_demand = df_demand[df_demand["n_missioni"]>0].reset_index(drop=True)

    # --- calcola severità coerente con la domanda simulata
    piv = df_demand.pivot_table(index="comune", columns="codice", values="n_missioni",
                                aggfunc="sum", fill_value=0).reset_index()
    for k in CODES:
        if k not in piv.columns: piv[k]=0
    piv["n_tot"] = piv[CODES].sum(axis=1)
    for k in CODES:
        piv[f"pct_{k.lower()}"] = (piv[k]/piv["n_tot"]).where(piv["n_tot"]>0,0.0)

    # score
    W = DEFAULT_WEIGHTS
    piv["severity_raw"] = W["ROSSO"]*piv["ROSSO"] + W["GIALLO"]*piv["GIALLO"] + W["VERDE"]*piv["VERDE"] + W["BIANCO"]*piv["BIANCO"]
    piv["severity_mean"] = (piv["severity_raw"]/piv["n_tot"]).where(piv["n_tot"]>0,0.0)
    piv["severity_per_100_calls"] = piv["severity_mean"]*100.0

    # unisci tier assegnato inizialmente (così restano coerenti)
    df_sev = piv.merge(df_tier, on="comune", how="left")
    df_sev["sample_flag"] = df_sev["n_tot"].map(lambda n: "SMALL_SAMPLE" if n < 50 else "")

    # --- domanda pesata per tier
    tier_weights = parse_kv(args.tier_weights, keys=["ALTA","MEDIA","BASSA"], cast=float) or {"ALTA":1.30,"MEDIA":1.10,"BASSA":1.00}
    df_demand = df_demand.merge(df_sev[["comune","severity_tier"]], on="comune", how="left")
    df_demand["tier_weight"] = df_demand["severity_tier"].map(tier_weights).fillna(1.0)
    df_demand["n_missioni_pesate"] = (df_demand["n_missioni"] * df_demand["tier_weight"]).round(2)

    # --- soglie LEA per-comune
    lea_base = parse_kv(args.lea_base, keys=CODES, cast=float) or {"ROSSO":8,"GIALLO":20,"VERDE":30,"BIANCO":45}
    lea_delta = parse_kv(args.lea_delta, keys=["ALTA","MEDIA","BASSA"], cast=float) or {"ALTA":-2,"MEDIA":-1,"BASSA":0}
    thr_rows=[]
    for _, r in df_sev[["comune","severity_tier"]].iterrows():
        cm, tr = r["comune"], r["severity_tier"]
        thr_rows.append({
            "comune": cm,
            "T_ROSSO":  max(1, int(round(lea_base["ROSSO"]  + lea_delta[tr]))),
            "T_GIALLO": max(1, int(round(lea_base["GIALLO"] + lea_delta[tr]))),
            "T_VERDE":  max(1, int(round(lea_base["VERDE"]  + lea_delta[tr]))),
            "T_BIANCO": max(1, int(round(lea_base["BIANCO"] + lea_delta[tr]))),
        })
    df_thr = pd.DataFrame(thr_rows)

    # --- salva
    out_dem = os.path.join(args.out_dir, "demand_by_comune_code.csv")
    out_sev = os.path.join(args.out_dir, "severita_comuni.csv")
    out_wgt = os.path.join(args.out_dir, "weighted_demand_by_comune_code.csv")
    out_thr = os.path.join(args.out_dir, "thresholds_by_comune.csv")

    df_demand.to_csv(out_dem, index=False)
    df_sev[[
        "comune","n_tot","ROSSO","GIALLO","VERDE","BIANCO",
        "pct_rosso","pct_giallo","pct_verde","pct_bianco",
        "severity_raw","severity_mean","severity_per_100_calls",
        "severity_tier","sample_flag"
    ]].sort_values(["severity_tier","severity_mean","n_tot"], ascending=[True,False,False]).to_csv(out_sev, index=False)
    df_demand[["comune","codice","n_missioni","severity_tier","tier_weight","n_missioni_pesate"]].to_csv(out_wgt, index=False)
    df_thr.to_csv(out_thr, index=False)

    # --- print riepilogo
    tot = int(df_demand["n_missioni"].sum())
    by_code = df_demand.groupby("codice")["n_missioni"].sum().to_dict()
    tiers_count = df_sev["severity_tier"].value_counts().to_dict()
    print(f"[OK] Salvato in: {args.out_dir}")
    print(f" - demand_by_comune_code.csv  (righe: {len(df_demand)})  tot_missioni={tot}  per codice={by_code}")
    print(f" - severita_comuni.csv        (comuni: {len(df_sev)})    tier_count={tiers_count}")
    print(f" - weighted_demand_by_comune_code.csv (righe: {len(df_demand)})")
    print(f" - thresholds_by_comune.csv   (righe: {len(df_thr)})")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--comuni-csv", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=118)
    ap.add_argument("--total-missions", type=int, default=20000)
    ap.add_argument("--mix-high", default="0.25,0.40,0.30,0.05")
    ap.add_argument("--mix-med",  default="0.15,0.35,0.40,0.10")
    ap.add_argument("--mix-low",  default="0.08,0.25,0.50,0.17")
    ap.add_argument("--tier-shares", default="ALTA=0.25,MEDIA=0.45,BASSA=0.30")
    ap.add_argument("--tier-weights", default="ALTA=1.30,MEDIA=1.10,BASSA=1.00")
    ap.add_argument("--lea-base", default="ROSSO=8,GIALLO=20,VERDE=30,BIANCO=45")
    ap.add_argument("--lea-delta", default="ALTA=-2,MEDIA=-1,BASSA=0")
    args = ap.parse_args()
    main(args)
