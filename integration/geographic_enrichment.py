from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


class GeographyEnrichmentError(RuntimeError):
    """Errore durante l'enrichment geografico sintetico."""
    pass


# ============================================================
# COLUMN DETECTION
# ============================================================

MUNICIPALITY_COLUMNS = (
    "comune",
    "municipality",
    "nome_comune",
    "comune_nome",
    "name",
    "nome",
    "comune di residenza"
)

LATITUDE_COLUMNS = (
    "lat",
    "latitude",
    "latitudine",
)

LONGITUDE_COLUMNS = (
    "lon",
    "lng",
    "long",
    "longitude",
    "longitudine",
)

POPULATION_COLUMNS = (
    "population",
    "popolazione",
    "residenti",
    "abitanti",
)

PROVINCE_COLUMNS = (
    "province",
    "provincia",
    "prov",
)


def _find_column(dataframe: pd.DataFrame, candidates: tuple[str, ...], ) -> str | None:
    normalized = {str(column).strip().lower(): column for column in dataframe.columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]

    return None


# MUNICIPALITY CATALOG
def load_municipality_catalog(catalog_path: Path, ) -> pd.DataFrame:
    catalog_path = Path(catalog_path)
    if not catalog_path.is_file():
        raise GeographyEnrichmentError(f"Catalogo dei comuni non trovato: {catalog_path}")

    try:
        catalog = pd.read_csv(catalog_path, encoding="utf-8-sig")
    except Exception as exc:
        raise GeographyEnrichmentError("Impossibile leggere il catalogo dei comuni.") from exc

    municipality_column = _find_column(catalog, MUNICIPALITY_COLUMNS)
    latitude_column = _find_column(catalog, LATITUDE_COLUMNS)
    longitude_column = _find_column(catalog, LONGITUDE_COLUMNS)

    if municipality_column is None:
        raise GeographyEnrichmentError("Nel catalogo non è stata trovata la colonna del comune.")

    if latitude_column is None:
        raise GeographyEnrichmentError("Nel catalogo non è stata trovata la colonna della latitudine.")

    if longitude_column is None:
        raise GeographyEnrichmentError("Nel catalogo non è stata trovata la colonna della longitudine.")

    population_column = _find_column(catalog, POPULATION_COLUMNS)
    province_column = _find_column(catalog, PROVINCE_COLUMNS, )
    standardized = pd.DataFrame()
    standardized["municipality"] = (catalog[municipality_column].astype(str).str.strip())
    standardized["latitude"] = pd.to_numeric(catalog[latitude_column], errors="coerce")
    standardized["longitude"] = pd.to_numeric(catalog[longitude_column], errors="coerce")

    if province_column is not None:
        standardized["province"] = (catalog[province_column].astype(str).str.strip())

    else:
        standardized["province"] = None

    # OPTIONAL POPULATION WEIGHTS
    if population_column is not None:
        standardized["population_weight"] = (
            pd.to_numeric(catalog[population_column], errors="coerce").fillna(0).clip(lower=0))
    else:
        # Se il CSV non contiene la popolazione, tutti i comuni hanno lo stesso peso.
        standardized["population_weight"] = 1.0

    # CLEANING
    standardized = standardized.loc[
        standardized["municipality"].ne("") & standardized["latitude"].notna() & standardized[
            "longitude"].notna()].copy()
    standardized = standardized.loc[
        standardized["latitude"].between(-90, 90) & standardized["longitude"].between(-180, 180)].copy()
    standardized = (standardized.drop_duplicates(subset=["municipality"], keep="first").reset_index(drop=True))
    if standardized.empty:
        raise GeographyEnrichmentError("Il catalogo geografico non contiene comuni validi con coordinate.")

    # Se i pesi sono tutti zero, torniamo a distribuzione uniforme.
    if standardized["population_weight"].sum() <= 0:
        standardized["population_weight"] = 1.0

    standardized["assignment_probability"] = (
                standardized["population_weight"] / standardized["population_weight"].sum())
    return standardized


# DETERMINISTIC ASSIGNMENT
def derive_geography_seed(experiment_seed: int) -> int:
    """
    Deriva un seed dedicato alla simulazione geografica dal seed principale dell'esperimento.
    """

    payload = f"prometheus-geography|{int(experiment_seed)}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8).digest()

    return int.from_bytes(digest, byteorder="big", signed=False) % (2 ** 32)


def _deterministic_unit_value(*, seed: int, patient_id: object) -> float:
    """
    Restituisce un valore deterministico in [0, 1) basato esclusivamente su seed + patient_id.
    """
    payload = f"{int(seed)}|{patient_id}".encode("utf-8")
    digest = hashlib.blake2b(payload, digest_size=8, ).digest()
    integer_value = int.from_bytes(digest, byteorder="big", signed=False, )

    return integer_value / float(2 ** 64)


# RESULTS ENRICHMENT
def enrich_stratification_with_geography(
    *,
    results: pd.DataFrame,
    catalog_path: Path,
    seed: int,
    residence_overrides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Aggiunge la residenza ai risultati finali dopo che PROMETHEUS
    ha terminato recommendation e allocation.

    Comportamento:
    - senza residence_overrides: comportamento storico invariato, tutta la geografia viene simulata deterministicamente;
    - con residence_overrides:
        le residenze reali vengono preservate e NON vengono simulate;
        la simulazione deterministica viene eseguita solo per le righe senza residenza reale.
    """

    if "patient_id" not in results.columns:
        raise GeographyEnrichmentError("patient_id non presente nei risultati.")

    if results["patient_id"].duplicated().any():
        raise GeographyEnrichmentError("patient_id duplicato nei risultati da arricchire geograficamente.")

    enriched = results.reset_index(drop=True).copy()
    enriched["residence_municipality"] = pd.NA
    enriched["residence_province"] = pd.NA
    enriched["residence_latitude"] = np.nan
    enriched["residence_longitude"] = np.nan
    enriched["residence_postal_code"] = pd.NA
    enriched["residence_data_status"] = pd.NA

    real_statuses = {
        "real_municipality",
        "real_postal_code",
        "real_municipality_verified_by_postal_code",
    }

    override_lookup = None
    real_override_ids: set[str] = set()

    # 1. VALIDAZIONE OVERRIDE
    if residence_overrides is not  None and not residence_overrides.empty:

        if "patient_id" not in residence_overrides.columns:
            raise GeographyEnrichmentError("residence_overrides non contiene patient_id.")

        if "residence_data_status" not in residence_overrides.columns:
            raise GeographyEnrichmentError("residence_overrides non contiene residence_data_status.")

        if residence_overrides["patient_id"].duplicated().any():
            raise GeographyEnrichmentError("patient_id duplicato in residence_overrides.")

        result_ids = set(enriched["patient_id"].astype(str))
        override_ids = set(residence_overrides["patient_id"].astype(str))
        unknown_ids = override_ids - result_ids

        if unknown_ids:
            raise GeographyEnrichmentError(f"residence_overrides contiene patient_id non presenti nei risultati: {sorted(unknown_ids)[:20]}")
        overrides = residence_overrides.copy()
        overrides["_patient_id_key"] = (overrides["patient_id"].astype(str))
        overrides["residence_data_status"] = (overrides["residence_data_status"].fillna("").astype(str).str.strip())
        allowed_statuses = (real_statuses | {"synthetic_fallback_pending"})
        invalid_statuses = sorted(set(overrides["residence_data_status"]) - allowed_statuses)

        if invalid_statuses:
            raise GeographyEnrichmentError(f"Stato geografico non riconosciuto nei residence_overrides: {invalid_statuses[:20]}")
        override_lookup = (overrides.set_index("_patient_id_key", drop=False))
        real_override_ids = set(overrides.loc[overrides["residence_data_status"].isin(real_statuses), "_patient_id_key"])


    # 2. SIMULAZIONE SOLO DOVE MANCA LA RESIDENZA REALE
    synthetic_positions = [
        position
        for position, patient_id
        in enumerate(enriched["patient_id"])
        if str(patient_id) not in real_override_ids
    ]

    if synthetic_positions:
        catalog = load_municipality_catalog(catalog_path)
        probabilities = (catalog["assignment_probability"].to_numpy(dtype=float))
        cumulative = np.cumsum(probabilities)

        cumulative[-1] = 1.0
        selected_indices: list[int] = []

        for position in synthetic_positions:
            patient_id = enriched.at[position, "patient_id"]
            value = _deterministic_unit_value(seed=seed, patient_id=patient_id)
            index = int(np.searchsorted(cumulative, value, side="right"))
            index = min(index, len(catalog) - 1)
            selected_indices.append(index)

        selected = (catalog.iloc[selected_indices].reset_index(drop=True))
        enriched.loc[synthetic_positions, "residence_municipality"] = selected["municipality"].to_numpy()
        enriched.loc[synthetic_positions, "residence_province"] = selected["province"].to_numpy()
        enriched.loc[synthetic_positions, "residence_latitude"] = selected["latitude"].to_numpy(dtype=float)
        enriched.loc[synthetic_positions, "residence_longitude"] = selected["longitude"].to_numpy(dtype=float)
        enriched.loc[synthetic_positions, "residence_data_status"] = ("synthetic_posthoc_not_ranker_input")


    # 3. NESSUN OVERRIDE
    if override_lookup is None:
        return enriched


    # 4. APPLICA LE RESIDENZE REALI
    for position, patient_id in enumerate(enriched["patient_id"]):
        patient_key = str(patient_id)

        if patient_key not in override_lookup.index:
            continue

        override = override_lookup.loc[patient_key]
        status = str(override.get("residence_data_status", "")).strip()

        if status == "synthetic_fallback_pending":
            continue

        if status not in real_statuses:
            raise GeographyEnrichmentError(f"Stato geografico non riconosciuto nei residence_overrides: {status!r}")

        municipality = override.get("residence_municipality")
        latitude = override.get("residence_latitude")
        longitude = override.get("residence_longitude")

        if pd.isna(municipality) or pd.isna(latitude) or pd.isna(longitude):
            raise GeographyEnrichmentError("Una residenza marcata come reale non contiene comune e coordinate complete.")

        enriched.at[position, "residence_municipality"] = str(municipality).strip()
        enriched.at[position, "residence_latitude"] = float(latitude)
        enriched.at[position, "residence_longitude"] = float(longitude)
        postal_code = override.get("residence_postal_code")

        if postal_code is not None and not pd.isna(postal_code) and str(postal_code).strip():
            enriched.at[position, "residence_postal_code"] = str(postal_code).strip()
        enriched.at[position, "residence_province"] = "Benevento"
        enriched.at[position, "residence_data_status"] = status

    return enriched

__all__ = [
    "GeographyEnrichmentError",
    "derive_geography_seed",
    "load_municipality_catalog",
    "enrich_stratification_with_geography",
]
