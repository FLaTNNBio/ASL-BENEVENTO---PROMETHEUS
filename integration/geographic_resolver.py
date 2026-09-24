from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

import pandas as pd


class GeographyResolutionError(ValueError):
    """Errore nella risoluzione della residenza reale."""
    pass


def _is_missing_value(value: object) -> bool:
    if value is None:
        return True

    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass

    return str(value).strip() == ""

# ============================================================
# NORMALIZATION
# ============================================================

def normalize_municipality_key(value: object) -> str:
    """
    Normalizza un nome di comune esclusivamente per il matching.

    Esempio:
        "Sant'Agata De' Goti"
        -> "sant agata de goti"
    """

    if _is_missing_value(value):
        return ""

    text = str(value).strip()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower()

    # Uniforma apostrofi e altra punteggiatura.
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return " ".join(text.split())


def normalize_postal_code(value: object) -> str:
    """
    Normalizza un CAP italiano come stringa di 5 cifre.

    Importante:
    il CAP NON viene trattato come quantità numerica.
    """

    if _is_missing_value(value):
        return ""

    if isinstance(value, float):
        if math.isnan(value):
            return ""

        if value.is_integer():
            value = int(value)

    text = str(value).strip()

    if not text:
        return ""

    # Caso frequente dopo lettura CSV/Excel:
    # 82100.0
    match = re.fullmatch(
        r"(\d{5})\.0+",
        text,
    )

    if match:
        text = match.group(1)

    if not re.fullmatch(r"\d{5}", text):
        raise GeographyResolutionError(
            f"CAP non valido: {value!r}. "
            "È richiesto un codice di 5 cifre."
        )

    return text


# ============================================================
# MUNICIPALITY CATALOG
# ============================================================

def load_municipality_lookup(
    catalog_path: Path,
) -> dict[str, dict]:
    """
    Carica il catalogo geografico dei comuni.

    Schema atteso compatibile con:
        comune, lat, lon
    """

    catalog_path = Path(catalog_path)

    if not catalog_path.is_file():
        raise GeographyResolutionError(
            "Catalogo comuni non trovato: "
            f"{catalog_path}"
        )

    frame = pd.read_csv(
        catalog_path,
        encoding="utf-8-sig",
    )

    normalized_columns = {
        str(column).strip().lower(): column
        for column in frame.columns
    }

    municipality_column = None

    for candidate in (
        "comune",
        "municipality",
        "nome_comune",
        "comune_nome",
    ):
        if candidate in normalized_columns:
            municipality_column = (
                normalized_columns[candidate]
            )
            break

    latitude_column = None

    for candidate in (
        "lat",
        "latitude",
    ):
        if candidate in normalized_columns:
            latitude_column = (
                normalized_columns[candidate]
            )
            break

    longitude_column = None

    for candidate in (
        "lon",
        "lng",
        "longitude",
    ):
        if candidate in normalized_columns:
            longitude_column = (
                normalized_columns[candidate]
            )
            break

    if municipality_column is None:
        raise GeographyResolutionError(
            "Colonna del comune non trovata "
            "nel catalogo geografico."
        )

    if latitude_column is None:
        raise GeographyResolutionError(
            "Colonna latitudine non trovata "
            "nel catalogo geografico."
        )

    if longitude_column is None:
        raise GeographyResolutionError(
            "Colonna longitudine non trovata "
            "nel catalogo geografico."
        )

    lookup: dict[str, dict] = {}

    for _, row in frame.iterrows():

        municipality = str(
            row[municipality_column]
        ).strip()

        key = normalize_municipality_key(
            municipality
        )

        if not key:
            continue

        # Eventuali duplicati dovuti esclusivamente
        # alla capitalizzazione vengono considerati
        # lo stesso comune.
        if key in lookup:
            continue

        lookup[key] = {
            "municipality": municipality,
            "latitude": float(
                row[latitude_column]
            ),
            "longitude": float(
                row[longitude_column]
            ),
        }

    if not lookup:
        raise GeographyResolutionError(
            "Il catalogo geografico non contiene "
            "comuni validi."
        )

    return lookup


# ============================================================
# POSTAL CODE CATALOG
# ============================================================

def load_postal_lookup(
    catalog_path: Path,
) -> dict[str, set[str]]:
    """
    Carica il catalogo CAP -> comuni.

    Schema:
        postal_code,municipality

    Un CAP può essere associato a più comuni:
    questa eventualità viene mantenuta esplicitamente.
    """

    catalog_path = Path(catalog_path)

    if not catalog_path.is_file():
        raise GeographyResolutionError(
            "Catalogo CAP non trovato: "
            f"{catalog_path}"
        )

    frame = pd.read_csv(
        catalog_path,
        dtype=str,
        encoding="utf-8-sig",
    )

    required = {
        "postal_code",
        "municipality",
    }

    missing = required - set(frame.columns)

    if missing:
        raise GeographyResolutionError(
            "Catalogo CAP non valido. "
            f"Colonne mancanti: {sorted(missing)}"
        )

    lookup: dict[str, set[str]] = {}

    for _, row in frame.iterrows():

        postal_code = normalize_postal_code(
            row["postal_code"]
        )

        municipality_key = (
            normalize_municipality_key(
                row["municipality"]
            )
        )

        if not postal_code or not municipality_key:
            continue

        lookup.setdefault(
            postal_code,
            set(),
        ).add(
            municipality_key
        )

    return lookup


# ============================================================
# REAL RESIDENCE RESOLUTION
# ============================================================

def resolve_real_residence(
    *,
    municipality_value: object = None,
    postal_code_value: object = None,
    municipality_lookup: dict[str, dict],
    postal_lookup: dict[str, set[str]],
) -> dict | None:
    """
    Risolve la geografia reale fornita dal CSV.

    Priorità:

    1. comune presente -> usa il comune reale;
    2. CAP presente -> risolve il comune dal CAP;
    3. entrambi -> devono essere coerenti;
    4. entrambi assenti -> None, quindi il chiamante
       potrà applicare il fallback sintetico.

    Un dato reale presente ma invalido NON viene
    mai sostituito silenziosamente con simulazione.
    """

    municipality_present = not _is_missing_value(
        municipality_value
    )

    postal_present = not _is_missing_value(
        postal_code_value
    )

    municipality_text = (
        str(municipality_value).strip()
        if municipality_present
        else ""
    )

    postal_text = (str(postal_code_value).strip() if postal_present else "" )

    # --------------------------------------------------------
    # Nessuna geografia reale disponibile
    # --------------------------------------------------------

    if (
        not municipality_present
        and not postal_present
    ):
        return None

    municipality_key = None
    municipality_record = None

    # --------------------------------------------------------
    # Comune fornito
    # --------------------------------------------------------

    if municipality_present:

        municipality_key = (
            normalize_municipality_key(
                municipality_text
            )
        )

        municipality_record = (
            municipality_lookup.get(
                municipality_key
            )
        )

        if municipality_record is None:
            raise GeographyResolutionError(
                "Comune di residenza non riconosciuto: "
                f"{municipality_text!r}"
            )

    # --------------------------------------------------------
    # CAP fornito
    # --------------------------------------------------------

    postal_code = None
    postal_candidates: set[str] | None = None

    if postal_present:

        postal_code = normalize_postal_code(
            postal_code_value
        )

        postal_candidates = postal_lookup.get(
            postal_code
        )

        if not postal_candidates:
            raise GeographyResolutionError(
                "CAP non riconosciuto nel territorio "
                f"supportato: {postal_code}"
            )

        # Rimuove eventuali associazioni verso comuni
        # che non esistono nel catalogo GIS corrente.
        postal_candidates = {
            key
            for key in postal_candidates
            if key in municipality_lookup
        }

        if not postal_candidates:
            raise GeographyResolutionError(
                "Il CAP è presente nel catalogo, "
                "ma non corrisponde ad alcun comune "
                "del territorio GIS supportato: "
                f"{postal_code}"
            )

    # --------------------------------------------------------
    # Comune + CAP
    # --------------------------------------------------------

    if (
        municipality_record is not None
        and postal_code is not None
    ):

        if municipality_key not in postal_candidates:
            raise GeographyResolutionError(
                "Comune e CAP non sono coerenti: "
                f"comune={municipality_text!r}, "
                f"CAP={postal_code}"
            )

        return {
            **municipality_record,
            "postal_code": postal_code,
            "residence_data_status":
                "real_municipality_verified_by_postal_code",
        }

    # --------------------------------------------------------
    # Solo comune
    # --------------------------------------------------------

    if municipality_record is not None:

        return {
            **municipality_record,
            "postal_code": None,
            "residence_data_status":
                "real_municipality",
        }

    # --------------------------------------------------------
    # Solo CAP
    # --------------------------------------------------------

    assert postal_code is not None
    assert postal_candidates is not None

    if len(postal_candidates) > 1:

        municipalities = sorted(
            municipality_lookup[key][
                "municipality"
            ]
            for key in postal_candidates
        )

        raise GeographyResolutionError(
            "CAP ambiguo: non identifica "
            "univocamente il comune di residenza. "
            f"CAP={postal_code}, "
            f"comuni={municipalities}"
        )

    resolved_key = next(
        iter(postal_candidates)
    )

    return {
        **municipality_lookup[
            resolved_key
        ],
        "postal_code": postal_code,
        "residence_data_status":
            "real_postal_code",
    }


__all__ = [
    "GeographyResolutionError",
    "normalize_municipality_key",
    "normalize_postal_code",
    "load_municipality_lookup",
    "load_postal_lookup",
    "resolve_real_residence",
]