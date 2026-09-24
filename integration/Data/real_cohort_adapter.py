from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from integration.geographic_resolver import (
    load_municipality_lookup,
    load_postal_lookup,
    resolve_real_residence,
)

from .csv_upload_service import (
    resolve_staged_patient_csv,
)

from .schema_validator import (
    NUMERIC_PATIENT_COLUMNS,
    REQUIRED_PATIENT_COLUMNS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MUNICIPALITY_CATALOG_PATH = (
        PROJECT_ROOT
        / "Ambulanze-main"
        / "AmbulanzeASL"
        / "dataset"
        / "data"
        / "comuni_geocoded.csv"
)

POSTAL_CATALOG_PATH = (
        PROJECT_ROOT
        / "integration"
        / "Data"
        / "Geography"
        / "benevento_postal_codes.csv"
)

MONTHLY_HISTORY_COLUMNS = (
    "patient_id",
    "month_offset",
    "calendar_month",
    "encounter_count",
    "emergency_count",
    "inpatient_count",
    "procedure_count",
    "careplan_count",
    "active_medication_count",
)


class RealCohortAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class RealCohort:
    """
    Coorte reale adattata al contratto PROMETHEUS.
    patients:contiene ESCLUSIVAMENTE le 34 colonne patient-level canoniche utilizzabili dalla pipeline.
    geography:è mantenuta separata e non è input del causal ranker.
    monthly_history: è intenzionalmente vuoto nella versione CSV patient-level.Le covariate aggregate necessarie sono già fornite nel CSV.
    """

    patients: pd.DataFrame
    geography: pd.DataFrame
    monthly_history: pd.DataFrame
    upload_id: str
    metadata: dict[str, Any]


def _load_compatibility_report(csv_path: Path, ) -> dict[str, Any]:
    report_path = (csv_path.parent / "compatibility_report.json")
    if not report_path.is_file():
        raise RealCohortAdapterError("Compatibility Report non trovato per il dataset caricato.")

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))

    except Exception as exc:
        raise RealCohortAdapterError("Compatibility Report non leggibile.") from exc

    if report.get("can_run") is not True:
        raise RealCohortAdapterError("Il dataset non risulta compatibile con PROMETHEUS.")

    return report


def _build_geography(raw: pd.DataFrame, patients: pd.DataFrame, report: dict[str, Any], ) -> pd.DataFrame:
    geography_report = report.get("geography", {})
    municipality_column = (geography_report.get("municipality_column"))
    postal_code_column = (geography_report.get("postal_code_column"))
    municipality_lookup = (load_municipality_lookup(MUNICIPALITY_CATALOG_PATH))
    postal_lookup = (load_postal_lookup(POSTAL_CATALOG_PATH))
    records = []

    for position, (_, row) in enumerate(raw.iterrows()):
        patient_id = (patients.iloc[position]["patient_id"])
        municipality_value = (row.get(municipality_column) if municipality_column else None)
        postal_value = (row.get(postal_code_column) if postal_code_column else None)

        # Il file è già stato validato ma integrity check prima dell'esecuzione.
        resolved = resolve_real_residence(
            municipality_value=municipality_value,
            postal_code_value=postal_value,
            municipality_lookup=municipality_lookup,
            postal_lookup=postal_lookup,
        )

        if resolved is None:
            records.append(
                {
                    "patient_id": patient_id,
                    "residence_municipality": pd.NA,
                    "residence_postal_code": pd.NA,
                    "residence_latitude": pd.NA,
                    "residence_longitude": pd.NA,
                    "residence_data_status": "synthetic_fallback_pending",
                }
            )

            continue

        records.append(
            {
                "patient_id": patient_id,
                "residence_municipality": resolved["municipality"],
                "residence_postal_code": resolved.get("postal_code"),
                "residence_latitude": resolved["latitude"],
                "residence_longitude":resolved["longitude"],
                "residence_data_status": resolved["residence_data_status"],
            }
        )

    geography = pd.DataFrame(records)

    if len(geography) != len(patients):
        raise RealCohortAdapterError("Perdita di pazienti durante l'adattamento geografico.")

    if geography["patient_id"].duplicated().any():
        raise RealCohortAdapterError("Duplicazione patient_id nella geografia.")

    return geography


def _build_canonical_patients(raw: pd.DataFrame, report: dict[str, Any]) -> pd.DataFrame:
    mapping = (report.get("schema", {}).get("column_mapping", {}))

    missing_mapping = [
        column
        for column in REQUIRED_PATIENT_COLUMNS
        if column not in mapping
    ]

    if missing_mapping:
        raise RealCohortAdapterError(
            f"Il mapping validato non contiene tutte le colonne PROMETHEUS richieste: {missing_mapping}")

    source_to_canonical = {
        source: canonical
        for canonical, source
        in mapping.items()
    }

    renamed = raw.rename(columns=source_to_canonical)

    missing_after_rename = [
        column
        for column in REQUIRED_PATIENT_COLUMNS
        if column not in renamed.columns
    ]

    if missing_after_rename:
        raise RealCohortAdapterError(
            f"Impossibile costruire il dataset canonico. Colonne mancanti dopo il mapping: {missing_after_rename}")

    # WHITELIST:
    # nominativi, codice fiscale, email, colonne extra
    # e geografia NON entrano in patients.
    patients = renamed.loc[:, list(REQUIRED_PATIENT_COLUMNS)].copy()
    patients["patient_id"] = (patients["patient_id"].astype("string").str.strip())

    for column in NUMERIC_PATIENT_COLUMNS:
        patients[column] = pd.to_numeric(patients[column], errors="raise").astype(float)

    if patients["patient_id"].isna().any():
        raise RealCohortAdapterError("patient_id mancante dopo la canonicalizzazione.")

    if patients["patient_id"].duplicated().any():
        raise RealCohortAdapterError("patient_id duplicato dopo la canonicalizzazione.")
    return patients


def load_real_cohort(upload_id: str, ) -> RealCohort:
    """
    Carica un CSV già validato e costruisce la rappresentazione canonica utilizzabile in seguito dal runner PROMETHEUS.
    """

    csv_path = resolve_staged_patient_csv(upload_id)
    report = _load_compatibility_report(csv_path)

    try:
        raw = pd.read_csv(csv_path, encoding="utf-8-sig")
    except Exception as exc:
        raise RealCohortAdapterError("Impossibile rileggere il CSV validato.") from exc

    patients = _build_canonical_patients(raw, report)
    geography = _build_geography(raw, patients, report)

    # Il contratto CSV corrente è patient-level.
    monthly_history = pd.DataFrame(columns=list(MONTHLY_HISTORY_COLUMNS))
    status_counts = (geography["residence_data_status"].value_counts().to_dict())
    identifying_columns = (report.get("schema", {}).get("identifying_columns", []))

    metadata = {
        "source_type": "real_csv",
        "upload_id": str(upload_id),
        "original_filename": report.get("file", {}).get("name"),
        "patient_count": int(len(patients)),
        "patient_column_count": int(len(patients.columns)),
        "monthly_history_records": 0,
        "monthly_history_source": "not_provided_patient_level_csv",
        "geography_ranker_input": False,
        "geography_status_counts":
            {
                str(key): int(value)
                for key, value
                in status_counts.items()
            },
        "excluded_identifying_columns": list(identifying_columns),
    }

    return RealCohort(
        patients=patients,
        geography=geography,
        monthly_history=monthly_history,
        upload_id=str(upload_id),
        metadata=metadata,
    )


__all__ = [
    "RealCohort",
    "RealCohortAdapterError",
    "load_real_cohort",
]
