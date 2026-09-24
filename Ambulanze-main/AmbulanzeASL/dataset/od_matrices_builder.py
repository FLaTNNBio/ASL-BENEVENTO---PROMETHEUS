# -*- coding: utf-8 -*-
"""
od_matrices_builder.py

Cosa fa:
- Carica: presidi_attuali.csv, presidi_potenziali.csv, comuni.csv (prodotti dal tuo build_presidi_dataset_static.py)
- Geocoda (se mancano lat/lon): usa Nominatim per i comuni (con cache su file)
- Calcola matrici OD realistiche con OSRM (durata e distanza) e salva:
    - od_time_min.csv     (from_site_id, to_comune, time_min)
    - od_distance_km.csv  (from_site_id, to_comune, distance_km)

Requisiti:
  pip install requests geopy pandas
Per OSRM:
  - Consigliato: OSRM locale (Campania/Italia) su http://localhost:5000
  - In alternativa: public demo http://router.project-osrm.org (rate limit, non garantito)

Uso:
  python od_matrices_builder.py --data-dir /path/to/data --osrm-url http://localhost:5000

Suggerimento: metti un file "sites.csv" con lat/lon specifici dei presidi. Se non c'è, useremo i centroidi dei comuni dei presidi.
"""

import argparse
import os
import time
import json
import math
import re
from typing import Dict, Tuple, List

import pandas as pd
import requests

DELAY_GEOCODE = 1.2  # seconds between Nominatim calls (rispetta fair use)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def norm_name(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s).strip())
    s = s.replace("’", "'")
    return " ".join(w.capitalize() if "'" not in w else (w[0].upper()+w[1:]) for w in s.split())

def geocode_comune(name: str, session: requests.Session, country="Italy", prov_hint="Benevento", region_hint="Campania") -> Tuple[float,float]:
    q = f"{name}, Province of {prov_hint}, {region_hint}, {country}"
    params = {"q": q, "format": "jsonv2", "limit": 1}
    headers = {"User-Agent": "od_matrices_builder/1.0 (research; contact: you@example.com)"}
    r = session.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    arr = r.json()
    if not arr:
        # fallback: meno vincoli
        params = {"q": f"{name}, {region_hint}, {country}", "format": "jsonv2", "limit": 1}
        r = session.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        arr = r.json()
    if arr:
        lat = float(arr[0]["lat"])
        lon = float(arr[0]["lon"])
        return lat, lon
    raise RuntimeError(f"Geocode fallito per: {name}")

def ensure_geocodes(df_places: pd.DataFrame, cache_path: str) -> pd.DataFrame:
    """
    df_places: DataFrame con colonna 'comune' e opz. lat/lon
    Ritorna df con lat/lon riempiti dove mancanti, usando cache JSON su disco.
    """
    cache: Dict[str, Tuple[float,float]] = {}
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)

    sess = requests.Session()
    lats, lons = [], []
    for _, row in df_places.iterrows():
        name = norm_name(row["comune"])
        lat = row.get("lat", "")
        lon = row.get("lon", "")
        if lat != "" and lon != "" and not (pd.isna(lat) or pd.isna(lon)):
            lats.append(float(lat))
            lons.append(float(lon))
            continue
        if name in cache:
            lat, lon = cache[name]
            lats.append(lat); lons.append(lon)
            continue
        # geocode
        try:
            lat, lon = geocode_comune(name, sess)
            cache[name] = (lat, lon)
            lats.append(lat); lons.append(lon)
            time.sleep(DELAY_GEOCODE)
        except Exception as e:
            raise RuntimeError(f"Geocoding error for {name}: {e}")
    # save cache
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    out = df_places.copy()
    out["lat"] = lats
    out["lon"] = lons
    return out

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def osrm_table(coords_src: List[Tuple[float,float]], coords_dst: List[Tuple[float,float]], base_url: str) -> Tuple[List[List[float]], List[List[float]]]:
    """
    Ritorna (durations_matrix_sec, distances_matrix_m) usando OSRM /table.
    - coords_*: liste [(lat,lon), ...]
    Nota: ordine: sources rows, destinations columns.
    """
    # OSRM vuole lon,lat
    srcs = ["{:.6f},{:.6f}".format(lon,lat) for (lat,lon) in coords_src]
    dsts = ["{:.6f},{:.6f}".format(lon,lat) for (lat,lon) in coords_dst]

    # Limiti: public demo ~100, OSRM locale può gestire centinaia ma meglio chunkare.
    MAX = 80
    durations = [[math.nan for _ in range(len(dsts))] for __ in range(len(srcs))]
    distances = [[math.nan for _ in range(len(dsts))] for __ in range(len(srcs))]

    sess = requests.Session()
    for si, schunk in enumerate(chunked(list(enumerate(srcs)), MAX)):
        s_idx, s_vals = zip(*schunk)
        for dj, dchunk in enumerate(chunked(list(enumerate(dsts)), MAX)):
            d_idx, d_vals = zip(*dchunk)
            coords_all = ";".join(list(s_vals) + list(d_vals))
            src_idx = list(range(0, len(s_vals)))
            dst_idx = list(range(len(s_vals), len(s_vals)+len(d_vals)))
            params = {
                "sources": ";".join(map(str, src_idx)),
                "destinations": ";".join(map(str, dst_idx)),
                "annotations": "duration,distance"
            }
            url = f"{base_url.rstrip('/')}/table/v1/driving/{coords_all}"
            r = sess.get(url, params=params, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"OSRM table error {r.status_code}: {r.text[:200]}")
            dat = r.json()
            dur = dat.get("durations")
            dis = dat.get("distances")
            if dur is None or dis is None:
                raise RuntimeError("OSRM response missing durations/distances")
            # place in global matrices
            for i_loc, i_glob in enumerate(s_idx):
                for j_loc, j_glob in enumerate(d_idx):
                    durations[i_glob][j_glob] = dur[i_loc][j_loc]  # seconds
                    distances[i_glob][j_glob] = dis[i_loc][j_loc]  # meters
    return durations, distances

def main(data_dir: str, osrm_url: str):
    att_p = os.path.join(data_dir, "presidi_attuali.csv")
    pot_p = os.path.join(data_dir, "presidi_potenziali.csv")
    comuni_p = os.path.join(data_dir, "comuni.csv")

    if not (os.path.exists(att_p) and os.path.exists(pot_p) and os.path.exists(comuni_p)):
        raise FileNotFoundError("Servono presidi_attuali.csv, presidi_potenziali.csv e comuni.csv in --data-dir")

    df_att = pd.read_csv(att_p)
    df_pot = pd.read_csv(pot_p)
    df_comuni = pd.read_csv(comuni_p).drop_duplicates()

    # Build sites list (from presidi attuali+potenziali). Se non c'è sites.csv con lat/lon, useremo i centroidi dei comuni.
    # ✅ riga/blocco corretto
    df_sites = pd.concat(
        [
            df_att[["comune", "tipo_presidio"]],
            df_pot.assign(tipo_presidio="POT")[["comune", "tipo_presidio"]],
        ],
        ignore_index=True
    ).drop_duplicates()

    df_sites["site_id"] = (df_sites["tipo_presidio"].fillna("POT").str.upper() + "_" + df_sites["comune"].str.upper().str.replace(" ","_"))
    df_sites = df_sites.drop_duplicates(subset=["site_id","comune"]).reset_index(drop=True)

    # Geocode comuni (demand) + presidi (supply)
    comuni_cache = os.path.join(data_dir, "geocode_comuni_cache.json")
    sites_cache = os.path.join(data_dir, "geocode_sites_cache.json")

    df_comuni_geo = ensure_geocodes(df_comuni.rename(columns={"comune":"comune"})[["comune"]], comuni_cache)
    df_sites_geo  = ensure_geocodes(df_sites[["comune","site_id"]].rename(columns={"comune":"comune"}), sites_cache)

    # Build coordinate lists in matching order
    # Sources: sites
    src_coords = [(row["lat"], row["lon"]) for _, row in df_sites_geo.iterrows()]
    # Destinations: comuni
    dst_coords = [(row["lat"], row["lon"]) for _, row in df_comuni_geo.iterrows()]

    # Call OSRM table
    durations, distances = osrm_table(src_coords, dst_coords, osrm_url)

    # Save CSVs
    # od_time_min.csv
    rows_time = []
    for i, (_, srow) in enumerate(df_sites_geo.iterrows()):
        for j, (_, crow) in enumerate(df_comuni_geo.iterrows()):
            sec = durations[i][j]
            rows_time.append({
                "from_site_id": srow["site_id"],
                "to_comune": crow["comune"],
                "time_min": round(sec/60.0, 1) if isinstance(sec, (int,float)) else ""
            })
    pd.DataFrame(rows_time).to_csv(os.path.join(data_dir, "od_time_min.csv"), index=False)

    # od_distance_km.csv
    rows_dist = []
    for i, (_, srow) in enumerate(df_sites_geo.iterrows()):
        for j, (_, crow) in enumerate(df_comuni_geo.iterrows()):
            m = distances[i][j]
            rows_dist.append({
                "from_site_id": srow["site_id"],
                "to_comune": crow["comune"],
                "distance_km": round(m/1000.0, 2) if isinstance(m, (int,float)) else ""
            })
    pd.DataFrame(rows_dist).to_csv(os.path.join(data_dir, "od_distance_km.csv"), index=False)

    # Save geocoded copies for reference
    df_comuni_geo.to_csv(os.path.join(data_dir, "comuni_geocoded.csv"), index=False)
    df_sites_geo.to_csv(os.path.join(data_dir, "sites_geocoded.csv"), index=False)

    print("[OK] Salvate le matrici OD in:", data_dir)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, help="Directory con i CSV (presidi_*.csv, comuni.csv)")
    ap.add_argument("--osrm-url", default="http://router.project-osrm.org", help="Es. http://localhost:5000 per OSRM locale")
    args = ap.parse_args()
    main(args.data_dir, args.osrm_url)
