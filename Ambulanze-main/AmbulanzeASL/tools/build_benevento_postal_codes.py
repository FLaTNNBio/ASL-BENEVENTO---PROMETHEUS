from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from integration.geographic_resolver import (
    normalize_municipality_key,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]

SOURCE_URL = (
    "https://www.tuttitalia.it/"
    "campania/provincia-di-benevento/87-cap/"
)

GEOJSON_PATH = (
    PROJECT_ROOT
    / "integration"
    / "Data"
    / "Geography"
    / "benevento_municipalities_2026.geojson"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "integration"
    / "Data"
    / "Geography"
    / "benevento_postal_codes.csv"
)


def load_supported_municipalities() -> dict[str, str]:
    payload = json.loads(
        GEOJSON_PATH.read_text(
            encoding="utf-8"
        )
    )

    result: dict[str, str] = {}

    for feature in payload["features"]:

        municipality = str(
            feature["properties"]["municipality"]
        ).strip()

        key = normalize_municipality_key(
            municipality
        )

        result[key] = municipality

    return result


def load_remote_postal_codes() -> pd.DataFrame:
    tables = pd.read_html(
        SOURCE_URL
    )

    matched_tables = []

    for table in tables:

        normalized_columns = {
            str(column).strip().lower(): column
            for column in table.columns
        }

        if (
            "comune" not in normalized_columns
            or "cap" not in normalized_columns
        ):
            continue

        current = table.rename(
            columns={
                normalized_columns["comune"]:
                    "municipality",
                normalized_columns["cap"]:
                    "postal_code",
            }
        )[
            [
                "municipality",
                "postal_code",
            ]
        ].copy()

        matched_tables.append(
            current
        )

    if not matched_tables:
        raise RuntimeError(
            "Nessuna tabella Comune/CAP trovata "
            "nella sorgente."
        )

    # La pagina può suddividere l'elenco dei comuni
    # in più tabelle HTML. Vanno concatenate tutte.
    selected = pd.concat(
        matched_tables,
        ignore_index=True,
    )

    selected["municipality"] = (
        selected["municipality"]
        .astype(str)
        .str.strip()
    )

    selected["postal_code"] = (
        selected["postal_code"]
        .astype(str)
        .str.extract(
            r"(\d{5})",
            expand=False,
        )
    )

    selected = selected.dropna(
        subset=[
            "municipality",
            "postal_code",
        ]
    )

    selected["_key"] = (
        selected["municipality"]
        .map(
            normalize_municipality_key
        )
    )

    print(
        "TABELLE CAP TROVATE:",
        len(matched_tables),
    )

    print(
        "RIGHE CAP LETTE:",
        len(selected),
    )

    return selected


def main() -> None:
    supported = (
        load_supported_municipalities()
    )

    remote = (
        load_remote_postal_codes()
    )

    remote_keys = set(
        remote["_key"]
    )

    supported_keys = set(
        supported
    )

    missing = sorted(
        supported_keys
        - remote_keys
    )

    extra = sorted(
        remote_keys
        - supported_keys
    )

    print(
        "COMUNI GEOJSON:",
        len(supported_keys),
    )

    print(
        "COMUNI SORGENTE:",
        len(remote_keys),
    )

    print(
        "MANCANTI:",
        missing,
    )

    print(
        "EXTRA:",
        extra,
    )

    if missing or extra:
        raise RuntimeError(
            "Il catalogo CAP non coincide "
            "con il territorio PROMETHEUS."
        )

    output_rows = []

    for _, row in remote.iterrows():

        key = row["_key"]

        if key not in supported:
            continue

        output_rows.append(
            {
                "postal_code":
                    str(
                        row["postal_code"]
                    ).zfill(5),

                # Usiamo il nome canonico
                # del nostro GeoJSON.
                "municipality":
                    supported[key],
            }
        )

    output = pd.DataFrame(
        output_rows
    )

    output = (
        output
        .drop_duplicates()
        .sort_values(
            [
                "postal_code",
                "municipality",
            ]
        )
        .reset_index(drop=True)
    )

    municipality_count = (
        output[
            "municipality"
        ].nunique()
    )

    if municipality_count != 78:
        raise RuntimeError(
            "Numero comuni inatteso: "
            f"{municipality_count}"
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    cap_counts = (
        output
        .groupby("postal_code")[
            "municipality"
        ]
        .nunique()
        .sort_values(
            ascending=False
        )
    )

    ambiguous = (
        cap_counts[
            cap_counts > 1
        ]
    )

    print()
    print(
        "OUTPUT:",
        OUTPUT_PATH,
    )

    print(
        "RIGHE:",
        len(output),
    )

    print(
        "COMUNI:",
        municipality_count,
    )

    print(
        "CAP DISTINTI:",
        output["postal_code"].nunique(),
    )

    print(
        "CAP AMBIGUI:",
        len(ambiguous),
    )

    if not ambiguous.empty:

        print()
        print(
            "CAP condivisi da più comuni:"
        )

        for postal_code, count in (
            ambiguous.items()
        ):
            municipalities = (
                output.loc[
                    output[
                        "postal_code"
                    ]
                    == postal_code,
                    "municipality",
                ]
                .tolist()
            )

            print(
                f"  {postal_code}: "
                f"{count} comuni -> "
                f"{municipalities}"
            )


if __name__ == "__main__":
    main()