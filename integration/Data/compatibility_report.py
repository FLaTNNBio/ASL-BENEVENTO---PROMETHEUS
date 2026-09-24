from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .schema_validator import (
    DERIVED_PROMETHEUS_COLUMNS,
    REQUIRED_PATIENT_COLUMNS,
    validate_patient_csv,
)


CSV_CONTRACT_VERSION = "prometheus_patient_csv_v1"

CANONICAL_MUNICIPALITY_COLUMN = "residence_municipality"
CANONICAL_POSTAL_CODE_COLUMN = "residence_postal_code"


def build_patient_csv_compatibility_report(
    csv_path: Path,
    *,
    municipality_catalog_path: Path,
    postal_catalog_path: Path,
    min_patients: int = 100,
    max_patients: int = 5000,
) -> dict[str, Any]:
    """
    Costruisce il report di compatibilità mostrabile alla futura UI prima dell'esecuzione di PROMETHEUS.
    Non modifica il CSV.Non esegue PROMETHEUS.
    """

    csv_path = Path(csv_path)

    validation = validate_patient_csv(
        csv_path,
        municipality_catalog_path=municipality_catalog_path,
        postal_catalog_path=postal_catalog_path,
        min_patients=min_patients,
        max_patients=max_patients,
    )

    geography = validation.get("geography", {},)
    row_count = int(validation.get("row_count", 0,))
    missing_columns = list(validation.get("missing_required_columns", [],))
    required_columns = list(REQUIRED_PATIENT_COLUMNS)
    present_required_count = (len(required_columns) - len(missing_columns))
    real_municipality_rows = int(geography.get("real_municipality_rows", 0,))
    real_postal_code_rows = int(geography.get("real_postal_code_rows", 0))
    real_verified_rows = int(geography.get("real_verified_rows", 0))
    real_rows = (real_municipality_rows + real_postal_code_rows + real_verified_rows)
    synthetic_rows = int(geography.get("synthetic_fallback_rows", 0))
    invalid_rows = int(geography.get("invalid_rows", 0))
    compatible = bool(validation.get("compatible", False))

    return {
        "contract_version": CSV_CONTRACT_VERSION,
        "status": "compatible" if compatible else "incompatible",
        "can_run":compatible,
        "file": {
            "name": csv_path.name,
        },

        "dataset": {
            "patient_count": row_count,
            "min_supported_patients": int(min_patients),
            "max_supported_patients": int(max_patients),
        },

        "schema": {
            "required_columns": required_columns,
            "required_column_count": len(required_columns),
            "present_required_count": present_required_count,
            "missing_required_columns": missing_columns,
            "column_mapping": validation.get("column_mapping", {}),
            "aliased_columns": validation.get("aliased_columns", []),
            "identifying_columns": validation.get("identifying_columns", []),
            "derived_by_prometheus": list(DERIVED_PROMETHEUS_COLUMNS),
            "geography_columns": {
                "municipality": CANONICAL_MUNICIPALITY_COLUMN,
                "postal_code": CANONICAL_POSTAL_CODE_COLUMN,
            },
        },

        "geography": {
            "municipality_column": geography.get("municipality_column"),
            "postal_code_column": geography.get("postal_code_column"),
            "real_rows": real_rows,
            "real_municipality_rows": real_municipality_rows,
            "real_postal_code_rows": real_postal_code_rows,
            "real_verified_rows": real_verified_rows,
            "synthetic_fallback_rows": synthetic_rows,
            "invalid_rows": invalid_rows,
            # La geografia continua a NON essere utilizzata come feature del causal ranker.
            "ranker_input": False
        },

        "errors": list(validation.get("errors", [])),
        "warnings": list(validation.get("warnings", [])),
    }


def write_patient_csv_template(output_path: Path,) -> Path:
    """
    Scrive il template CSV ufficiale.
    Contiene:
    - le 34 colonne patient-level necessarie;
    - comune e CAP opzionali.
    Non contiene colonne identificative personali.
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [*REQUIRED_PATIENT_COLUMNS, CANONICAL_MUNICIPALITY_COLUMN, CANONICAL_POSTAL_CODE_COLUMN]
    template = pd.DataFrame(columns=columns)
    template.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


__all__ = [
    "CSV_CONTRACT_VERSION",
    "CANONICAL_MUNICIPALITY_COLUMN",
    "CANONICAL_POSTAL_CODE_COLUMN",
    "build_patient_csv_compatibility_report",
    "write_patient_csv_template",
]