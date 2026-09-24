#!/usr/bin/env python3
"""
make_comuni_geojson.py

Legge un CSV con una colonna "comune" e scarica i confini amministrativi
(Polygon/MultiPolygon) da Nominatim (OpenStreetMap), creando un GeoJSON
da usare nella tua app: dataset/data/comuni_benevento.geojson

USO:
    python make_comuni_geojson.py comuni.csv output.geojson

Se non specifichi niente, usa:
    input  = ./2ebdf76e-9ea6-4489-b5c9-1d6ca6f62f71.csv
    output = ./comuni_benevento.geojson

NOTE IMPORTANTI:
- Rispetta la policy di Nominatim: max 1 richiesta al secondo.
- Precisa un User-Agent riconoscibile con un contatto email.
- Limitiamo la ricerca a Provincia di Benevento (Campania, IT) con viewbox.

Dipendenze: solo 'requests' (pip install requests)
"""

import csv, json, time, sys, unicodedata, urllib.parse
from pathlib import Path

try:
    import requests
except Exception:
    print("Devi installare 'requests' (pip install requests)")
    sys.exit(1)

# Bounding box approssimata Benevento (SW, NE)
BBOX = {
    "left": 14.20,
    "bottom": 40.85,
    "right": 15.25,
    "top": 41.60,
}

NOMINATIM = "https://nominatim.openstreetmap.org/search"

USER_AGENT = "ASL-BN118/1.0 (confini comuni; contact: you@example.com)"  # <-- metti un contatto reale

def normalize(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")  # toglie accenti
    s = s.replace("’", "'").replace("  ", " ")
    # Maiuscole/Minuscole formattate
    s = " ".join(w.capitalize() for w in s.split())
    return s

def pick_best(result_list):
    """Filtra i risultati: boundary amministrativo in IT, admin_level 8/7 (comuni)."""
    if not result_list:
        return None
    # preferisci boundary administrative relation
    scored = []
    for r in result_list:
        score = 0
        if r.get("geojson"):
            score += 2
        if r.get("category") == "boundary":
            score += 3
        if r.get("type") in ("administrative", "boundary"):
            score += 2
        if r.get("class") == "boundary":
            score += 2
        if r.get("addresstype") in ("city","town","village","municipality","administrative"):
            score += 1
        if r.get("osm_type") == "relation":
            score += 1
        # admin level (se presente)
        al = (r.get("extratags") or {}).get("admin_level") or (r.get("namedetails") or {}).get("admin_level")
        if al and str(al) in ("7","8"):
            score += 2
        # country
        if (r.get("address") or {}).get("country_code") == "it":
            score += 1
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]

def query_nominatim(name: str, delay_sec: float = 1.1):
    """Chiama Nominatim con viewbox Benevento e polygon_geojson=1."""
    params = {
        "q": f"{name}, Benevento, Campania, Italia",
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
        "polygon_geojson": 1,
        "bounded": 1,
        "viewbox": f"{BBOX['left']},{BBOX['top']},{BBOX['right']},{BBOX['bottom']}",
        "countrycodes": "it",
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(NOMINATIM, params=params, headers=headers, timeout=60)
    if r.status_code != 200:
        return None
    data = r.json()
    time.sleep(delay_sec)  # rispetto rate-limit
    return pick_best(data)

def load_names(csv_path: Path):
    # tenta sia , che ;
    for sep in (",",";","\t"):
        try:
            rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8"), delimiter=sep))
            if rows and "comune" in rows[0].keys():
                return [normalize(r["comune"]) for r in rows if r.get("comune")]
        except Exception:
            continue
    # fallback: una colonna, senza header
    names = []
    with csv_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().strip(",;")
            if line and line.lower() != "comune":
                names.append(normalize(line))
    return names

def main():
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/comuni.csv")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/comuni_benevento.geojson")

    if not inp.exists():
        print(f"Input non trovato: {inp}")
        sys.exit(2)

    names = load_names(inp)
    if not names:
        print("Nessun nome trovato nel CSV (serve una colonna 'comune').")
        sys.exit(3)

    print(f"Trovati {len(names)} comuni nel CSV.")
    features = []
    missing = []

    for i, raw in enumerate(names, 1):
        name = normalize(raw)
        print(f"[{i:02d}/{len(names)}] {name} ...", end="", flush=True)
        hit = query_nominatim(name)
        if not hit or "geojson" not in hit:
            print(" ❌ non trovato")
            missing.append(name)
            continue
        gj = hit["geojson"]
        # Fissa eventuali Polygon vs MultiPolygon
        geom_type = gj.get("type")
        if geom_type == "Polygon":
            geometry = {"type": "MultiPolygon", "coordinates": [gj["coordinates"]]}
        else:
            geometry = gj

        feat = {
            "type": "Feature",
            "properties": {
                "comune": name,
                "display_name": hit.get("display_name"),
                "source": "nominatim",
                "osm_id": hit.get("osm_id"),
                "osm_type": hit.get("osm_type"),
                "class": hit.get("class"),
                "type": hit.get("type"),
                "admin_level": (hit.get("extratags") or {}).get("admin_level")
            },
            "geometry": geometry
        }
        features.append(feat)
        print(" ✅")

    fc = {"type": "FeatureCollection", "features": features}
    out.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    print(f"\nSalvato: {out.resolve()}")
    if missing:
        print("\n⚠️ Non trovati ({0}): {1}".format(len(missing), ", ".join(missing)))

if __name__ == "__main__":
    main()
