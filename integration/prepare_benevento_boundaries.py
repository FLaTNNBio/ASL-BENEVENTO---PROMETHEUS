from __future__ import annotations

import json
import zipfile

from pathlib import Path

PROJECT_ROOT = (Path(__file__).resolve().parents[1])
GEOGRAPHY_ROOT = (PROJECT_ROOT / "integration" / "Data" / "Geography")
ISTAT_ROOT = (GEOGRAPHY_ROOT / "istat_2026")
OUTPUT_GEOJSON = (GEOGRAPHY_ROOT / "benevento_municipalities_2026.geojson")

# Codice ISTAT provincia di Benevento
BENEVENTO_PROVINCE_CODE = 62


def require_geopandas():
    try:

        import geopandas as gpd

    except ImportError as exc:

        raise RuntimeError(
            "GeoPandas non è installato. "
        ) from exc

    return gpd


def find_municipality_shapefile() -> Path:
    shapefiles = list(ISTAT_ROOT.rglob("*.shp"))

    if not shapefiles:
        raise FileNotFoundError("Nessuno shapefile trovatonell'archivio ISTAT.")

    municipality_candidates = [
        path
        for path in shapefiles
        if "com" in path.name.lower()
    ]

    if not municipality_candidates:
        print("Shapefile disponibili:")
        for path in shapefiles:
            print(" -", path)

        raise RuntimeError(
            "Non è stato possibile identificareautomaticamente lo shapefile comunale.")

    wgs_candidates = [path for path in municipality_candidates if "wgs" in path.name.lower()]

    if wgs_candidates:
        return wgs_candidates[0]

    return municipality_candidates[0]


def find_column(columns, candidates, ):
    normalized = {
        str(column).strip().lower():
            column
        for column in columns
    }

    for candidate in candidates:
        if candidate.lower() in normalized:
            return normalized[candidate.lower()]

    return None


def main():
    gpd = require_geopandas()
    print(
        "PREPARAZIONE CONFINI "
        "COMUNALI BENEVENTO ===\n"
    )

    shapefile = (find_municipality_shapefile())
    print("Shapefile comuni:", shapefile)
    municipalities = (gpd.read_file(shapefile))

    print("\nColonne ISTAT:")
    print(list(municipalities.columns))

    province_column = find_column(
        municipalities.columns,
        (
            "PRO_COM",
            "COD_PRO",
            "COD_PROV",
            "PROV",
            "PROV_CODE",
        ),
    )

    municipality_name_column = find_column(
        municipalities.columns,
        (
            "COMUNE",
            "DEN_COM",
            "DEN_CM",
            "NAME",
        ),
    )

    municipality_code_column = find_column(
        municipalities.columns,
        (
            "PRO_COM",
            "PRO_COM_T",
            "COD_COM",
        ),
    )

    if province_column is None:
        raise RuntimeError(
            "Colonna provincia ISTAT non identificata automaticamente.\n"
            f"Colonne disponibili: "
            f"{list(municipalities.columns)}"
        )

    if municipality_name_column is None:
        raise RuntimeError(
            "Colonna nome comune ISTAT non identificata automaticamente."
        )

    # Identificazione provincia
    province_numeric = (municipalities[province_column].astype(str).str.strip())

    # PRO_COM può contenere il codice comune completo in tal caso le prime cifre identificano la provincia.
    province_mask = (province_numeric.str.lstrip("0").str.startswith(str(BENEVENTO_PROVINCE_CODE)))

    benevento = (municipalities.loc[province_mask].copy())

    if benevento.empty:
        raise RuntimeError(
            "Nessun comune della provincia di Benevento identificato.\n Controllare le colonne stampate dallo script.")

    # Web map CRS
    benevento = (benevento.to_crs(epsg=4326))

    # Standardizzazione
    output = gpd.GeoDataFrame(
        {
            "municipality": benevento[municipality_name_column].astype(str).str.strip(),
            "istat_code": (benevento[municipality_code_column].astype(str).str.strip()
                           if municipality_code_column
                              is not None
                           else None
                           ),

            "geometry": benevento.geometry,
        },

        geometry="geometry",
        crs="EPSG:4326",
    )

    output = (output.drop_duplicates(subset=["municipality"]).sort_values("municipality").reset_index(drop=True))
    GEOGRAPHY_ROOT.mkdir(parents=True,exist_ok=True,)
    output.to_file(OUTPUT_GEOJSON,driver="GeoJSON",)

    print("\nComuni esportati:", len(output))
    print("\nPrimi comuni:")
    print(output[["municipality", "istat_code", ]].head(10))

    print("\nGeoJSON creato:")
    print(OUTPUT_GEOJSON)
    print("\nCRS:", output.crs)
    print("\nPreparazione completata.")


if __name__ == "__main__":
    main()
