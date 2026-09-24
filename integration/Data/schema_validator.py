from __future__ import annotations

from pathlib import Path
from typing import Any
import re
import unicodedata
from collections import defaultdict

import pandas as pd
import numpy as np

from integration.geographic_resolver import (
    GeographyResolutionError,
    load_municipality_lookup,
    load_postal_lookup,
    resolve_real_residence,
)

# ============================================================
# PATIENT-LEVEL CONTRACT
# ============================================================

REQUIRED_PATIENT_COLUMNS = (
    "patient_id",
    "age",
    "female",
    "deprivation_index",
    "rurality",
    "health_literacy_score",
    "smoking",
    "bmi",
    "diabetes",
    "cardiovascular_disease",
    "copd",
    "chronic_kidney_disease",
    "cancer_history",
    "mental_health_condition",
    "chronic_pain",
    "condition_distinct",
    "prior_inpatient",
    "prior_emergency",
    "medication_distinct",
    "recent_utilization_trend",
    "multimorbidity",
    "polypharmacy",
    "encounter_count",
    "days_since_encounter",
    "procedure_count",
    "careplan_count",
    "frailty_index",
    "functional_limitation_score",
    "social_fragility_score",
    "cognitive_impairment",
    "non_self_sufficiency",
    "caregiver_available",
    "housing_instability",
    "palliative_need",
)

# ============================================================
# CONTROLLED COLUMN ALIASES
# ============================================================

PATIENT_COLUMN_ALIASES = {
    "patient_id": (
        "id_paziente",
        "paziente_id",
    ),

    "age": (
        "eta",
        "età",
        "age_years",
    ),

    "female": (
        "sesso_femminile",
        "female_flag",
    ),

    "deprivation_index": (
        "indice_deprivazione",
    ),

    "rurality": (
        "ruralita",
        "ruralità",
    ),

    "health_literacy_score": (
        "indice_alfabetizzazione_sanitaria",
        "health_literacy",
    ),

    "smoking": (
        "fumatore",
    ),

    "bmi": (
        "imc",
    ),

    "diabetes": (
        "diabete",
    ),

    "cardiovascular_disease": (
        "malattia_cardiovascolare",
    ),

    "copd": (
        "bpco",
    ),

    "chronic_kidney_disease": (
        "malattia_renale_cronica",
    ),

    "cancer_history": (
        "storia_oncologica",
        "anamnesi_oncologica",
    ),

    "mental_health_condition": (
        "condizione_salute_mentale",
    ),

    "chronic_pain": (
        "dolore_cronico",
    ),

    "condition_distinct": (
        "condizioni_distinte",
        "numero_condizioni",
    ),

    "prior_inpatient": (
        "ricoveri_precedenti",
    ),

    "prior_emergency": (
        "accessi_emergenza_precedenti",
    ),

    "medication_distinct": (
        "farmaci_distinti",
    ),

    "recent_utilization_trend": (
        "trend_utilizzo_recente",
    ),

    "multimorbidity": (
        "multimorbidita",
        "multimorbidità",
    ),

    "polypharmacy": (
        "polifarmacia",
    ),

    "encounter_count": (
        "conteggio_incontri",
    ),

    "days_since_encounter": (
        "giorni_da_ultimo_incontro",
    ),

    "procedure_count": (
        "numero_procedure",
    ),

    "careplan_count": (
        "numero_piani_cura",
    ),

    "frailty_index": (
        "indice_fragilita",
        "indice_fragilità",
    ),

    "functional_limitation_score": (
        "punteggio_limitazione_funzionale",
    ),

    "social_fragility_score": (
        "punteggio_fragilita_sociale",
        "punteggio_fragilità_sociale",
    ),

    "cognitive_impairment": (
        "deficit_cognitivo",
    ),

    "non_self_sufficiency": (
        "non_autosufficienza",
    ),

    "caregiver_available": (
        "caregiver_disponibile",
    ),

    "housing_instability": (
        "instabilita_abitativa",
        "instabilità_abitativa",
    ),

    "palliative_need": (
        "bisogno_palliativo",
    ),
}

IDENTIFYING_COLUMN_ALIASES = (
    "nome",
    "cognome",
    "nominativo",
    "nome_cognome",
    "codice_fiscale",
    "cf",
    "email",
    "e_mail",
    "telefono",
    "numero_telefono",
    "cellulare",
    "indirizzo",
    "indirizzo_residenza",
)

NUMERIC_PATIENT_COLUMNS = tuple(
    column
    for column in REQUIRED_PATIENT_COLUMNS
    if column != "patient_id"
)

# ============================================================
# SEMANTIC DOMAINS
# ============================================================

BINARY_PATIENT_COLUMNS = (
    "female",
    "rurality",
    "smoking",
    "diabetes",
    "cardiovascular_disease",
    "copd",
    "chronic_kidney_disease",
    "cancer_history",
    "mental_health_condition",
    "chronic_pain",
    "multimorbidity",
    "polypharmacy",
    "cognitive_impairment",
    "non_self_sufficiency",
    "caregiver_available",
    "housing_instability",
    "palliative_need",
)

UNIT_INTERVAL_COLUMNS = (
    "deprivation_index",
    "health_literacy_score",
    "frailty_index",
    "functional_limitation_score",
    "social_fragility_score",
)

NONNEGATIVE_INTEGER_COLUMNS = (
    "condition_distinct",
    "prior_inpatient",
    "prior_emergency",
    "medication_distinct",
    "encounter_count",
    "procedure_count",
    "careplan_count",
)

# Range osservati sulla popolazione sintetica PROMETHEUS
# baseline, 5000 pazienti, seed=42.
#
# Questi NON sono domini rigidi: un valore esterno
# produce un warning, non rende il CSV incompatibile.
OBSERVED_REFERENCE_RANGES = {
    "age": (18.0, 99.0),
    "bmi": (16.0, 42.30135179710311),
    "condition_distinct": (0.0, 11.0),
    "prior_inpatient": (0.0, 15.0),
    "prior_emergency": (0.0, 14.0),
    "medication_distinct": (0.0, 18.0),
    "recent_utilization_trend": (
        -6.666666666666668,
        33.33333333333333,
    ),
    "encounter_count": (0.0, 442.0),
    "days_since_encounter": (
        0.005173612046145059,
        730.0,
    ),
    "procedure_count": (0.0, 20.0),
    "careplan_count": (0.0, 25.0),
}

# Questi campi vengono prodotti da PROMETHEUS.
# Non fanno parte dell'input reale necessario.
DERIVED_PROMETHEUS_COLUMNS = (
    "baseline_need_level",
    "baseline_need_score",
    "current_care_profile",
    "current_care_profile_level",
    "recommended_actionable_level",
    "recommended_profile_id",
)

# ============================================================
# GEOGRAPHY ALIASES
# ============================================================

MUNICIPALITY_ALIASES = (
    "residence_municipality",
    "comune_residenza",
    "municipality",
    "comune",
    "residence_comune",
    "Comune di residenza",
)

POSTAL_CODE_ALIASES = (
    "residence_postal_code",
    "postal_code",
    "cap",
    "zip_code",
    "zipcode",
)


def _normalize_header_name(value: object, ) -> str:
    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text, )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text, )
    return text.strip("_")


def _resolve_patient_column_mapping(frame: pd.DataFrame, ) -> tuple[dict[str, str], dict[str, list[str]],]:
    alias_to_canonical: dict[str, str] = {}
    for canonical in REQUIRED_PATIENT_COLUMNS:
        candidates = (canonical, *PATIENT_COLUMN_ALIASES.get(canonical, (), ),)

        for candidate in candidates:
            normalized = (_normalize_header_name(candidate))
            existing = (alias_to_canonical.get(normalized))
            if existing is not None and existing != canonical:
                raise RuntimeError(f"Alias interno ambiguo: {candidate!r} -> {existing!r}/{canonical!r}")
            alias_to_canonical[normalized] = canonical

    matched: dict[str, list[str],] = defaultdict(list)
    for source_column in frame.columns:
        normalized = (_normalize_header_name(source_column))
        canonical = (alias_to_canonical.get(normalized))
        if canonical is not None:
            matched[canonical].append(source_column)

    collisions = {
        canonical: sources
        for canonical, sources
        in matched.items()
        if len(sources) > 1
    }

    mapping = {
        canonical: sources[0]
        for canonical, sources
        in matched.items()
        if len(sources) == 1
    }

    return mapping, collisions


# ============================================================
# HELPERS
# ============================================================

def _find_column(
        frame: pd.DataFrame,
        aliases: tuple[str, ...],
) -> str | None:
    normalized = {
        str(column).strip().lower(): column
        for column in frame.columns
    }

    for alias in aliases:
        if alias.lower() in normalized:
            return normalized[alias.lower()]

    return None


def _json_safe_value(value: object) -> object:
    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return value


# ============================================================
# CSV VALIDATION
# ============================================================

def validate_patient_csv(
        csv_path: Path,
        *,
        municipality_catalog_path: Path | None = None,
        postal_catalog_path: Path | None = None,
        min_patients: int = 100,
        max_patients: int = 5000,
) -> dict[str, Any]:
    """
    Valida un CSV patient-level per la modalità real cohort.

    Questa funzione NON esegue PROMETHEUS e NON modifica
    il file originale.

    La compatibilità richiede:
    - tutte le covariate patient-level richieste;
    - patient_id valido e univoco;
    - covariate numeriche senza valori mancanti/non numerici;
    - numero pazienti compatibile con la modalità interactive;
    - geografia reale valida, se fornita.

    Comune/CAP completamente assenti sono consentiti:
    quella riga potrà usare successivamente il fallback sintetico.
    """

    csv_path = Path(csv_path)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not csv_path.is_file():
        return {
            "compatible": False,
            "errors": [{"code": "file_not_found", "message": f"CSV non trovato: {csv_path}", }],
            "warnings": [],
        }

    try:
        frame = pd.read_csv(csv_path, encoding="utf-8-sig", )
        patient_column_mapping, column_collisions = (_resolve_patient_column_mapping(frame))

        if column_collisions:
            errors.append(
                {
                    "code": "ambiguous_column_mapping",
                    "message": "Più colonne del CSV corrispondono alla stessa variabile PROMETHEUS.",
                    "columns": column_collisions,
                }
            )

        rename_map = {
            source: canonical
            for canonical, source
            in patient_column_mapping.items()
            if source != canonical
        }
        canonical_frame = (frame.rename(columns=rename_map).copy())
    except Exception as exc:
        return {
            "compatible": False,
            "errors": [{"code": "csv_read_error", "message": str(exc)}],
            "warnings": [],
        }

    row_count = len(frame)

    # --------------------------------------------------------
    # Population size
    # --------------------------------------------------------

    if row_count < min_patients:
        errors.append(
            {
                "code": "too_few_patients",
                "message": (
                    f"Il CSV contiene {row_count} pazienti; "
                    f"il minimo supportato è {min_patients}."
                ),
            }
        )

    if row_count > max_patients:
        errors.append(
            {
                "code": "too_many_patients",
                "message": (
                    f"Il CSV contiene {row_count} pazienti; "
                    f"il massimo supportato è {max_patients}."
                ),
            }
        )

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in REQUIRED_PATIENT_COLUMNS
        if column not in patient_column_mapping   and column not in column_collisions
    ]

    if missing_columns:
        errors.append(
            {
                "code": "missing_required_columns",
                "message": "Mancano colonne obbligatorie.",
                "columns": missing_columns,
            }
        )

    # --------------------------------------------------------
    # patient_id
    # --------------------------------------------------------

    if "patient_id" in frame.columns:

        patient_ids = (
            canonical_frame["patient_id"]
            .astype("string")
            .str.strip()
        )

        missing_ids = (
                patient_ids.isna()
                | patient_ids.eq("")
        )

        if missing_ids.any():
            errors.append(
                {
                    "code": "missing_patient_id",
                    "message": ("Sono presenti patient_id mancanti."),
                    "rows": [
                        int(index) + 2
                        for index in frame.index[
                                         missing_ids
                                     ][:20]
                    ],
                    "count": int(
                        missing_ids.sum()
                    ),
                }
            )

        duplicate_ids = (
                patient_ids.notna()
                & patient_ids.duplicated(
            keep=False
        )
        )

        if duplicate_ids.any():
            duplicate_values = sorted(
                patient_ids[
                    duplicate_ids
                ]
                .dropna()
                .unique()
                .tolist()
            )

            errors.append(
                {
                    "code": "duplicate_patient_id",
                    "message": (
                        "patient_id deve essere univoco."
                    ),
                    "count": int(
                        len(duplicate_values)
                    ),
                    "examples": (
                        duplicate_values[:20]
                    ),
                }
            )

    # --------------------------------------------------------
    # Numeric covariates
    # --------------------------------------------------------

    numeric_issues = []

    for column in NUMERIC_PATIENT_COLUMNS:

        if column not in canonical_frame.columns:
            continue

        raw = canonical_frame[column]

        converted = pd.to_numeric(
            raw,
            errors="coerce",
        )

        invalid_mask = (
                raw.notna()
                & converted.isna()
        )

        non_finite_mask = (
                converted.notna()
                & ~np.isfinite(
            converted.astype(float)
        )

        )

        missing_mask = (
                converted.isna()
                | non_finite_mask
        )

        if invalid_mask.any() or missing_mask.any():
            numeric_issues.append(
                {
                    "column": column,
                    "missing_or_invalid": int(
                        missing_mask.sum()
                    ),
                    "non_numeric": int(
                        invalid_mask.sum()
                    ),

                    "non_finite": int(
                        non_finite_mask.sum()
                    ),
                }
            )

    if numeric_issues:
        errors.append(
            {
                "code":
                    "invalid_numeric_covariates",
                "message": (
                    "Sono presenti valori mancanti "
                    "o non numerici nelle covariate "
                    "richieste."
                ),
                "columns": numeric_issues,
            }
        )

    # --------------------------------------------------------
    # Semantic domains
    # --------------------------------------------------------

    semantic_issues = []

    # --------------------------------------------------------
    # Binary features
    # --------------------------------------------------------

    for column in BINARY_PATIENT_COLUMNS:

        if column not in canonical_frame.columns:
            continue

        values = pd.to_numeric(
            canonical_frame[column],
            errors="coerce",
        )

        valid_values = values[
            values.notna()
            & np.isfinite(
                values.astype(float)
            )
            ]

        invalid_mask = ~valid_values.isin(
            [0.0, 1.0]
        )

        if invalid_mask.any():
            invalid_values = sorted(
                valid_values[
                    invalid_mask
                ]
                .unique()
                .tolist()
            )

            semantic_issues.append(
                {
                    "column": column,
                    "rule": "binary_0_1",
                    "message": (
                        f"{column} deve contenere "
                        "esclusivamente 0 oppure 1."
                    ),
                    "invalid_count": int(
                        invalid_mask.sum()
                    ),
                    "examples": (
                        invalid_values[:20]
                    ),
                }
            )

    # --------------------------------------------------------
    # Scores constrained to [0, 1]
    # --------------------------------------------------------

    for column in UNIT_INTERVAL_COLUMNS:

        if column not in frame.columns:
            continue

        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

        valid_values = values[
            values.notna()
            & np.isfinite(
                values.astype(float)
            )
            ]

        invalid_mask = (
                (valid_values < 0.0)
                | (valid_values > 1.0)
        )

        if invalid_mask.any():
            invalid_values = (
                valid_values[
                    invalid_mask
                ]
            )

            semantic_issues.append(
                {
                    "column": column,
                    "rule": "unit_interval",
                    "message": (
                        f"{column} deve essere "
                        "compreso tra 0 e 1."
                    ),
                    "invalid_count": int(
                        invalid_mask.sum()
                    ),
                    "observed_min": float(
                        invalid_values.min()
                    ),
                    "observed_max": float(
                        invalid_values.max()
                    ),
                }
            )

    # --------------------------------------------------------
    # Non-negative integer counts
    # --------------------------------------------------------

    for column in NONNEGATIVE_INTEGER_COLUMNS:

        if column not in frame.columns:
            continue

        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

        valid_values = values[
            values.notna()
            & np.isfinite(
                values.astype(float)
            )
            ]

        negative_mask = (
                valid_values < 0.0
        )

        non_integer_mask = (
                (
                        valid_values
                        - np.round(valid_values)
                ).abs()
                > 1e-9
        )

        invalid_mask = (
                negative_mask
                | non_integer_mask
        )

        if invalid_mask.any():
            invalid_values = (
                valid_values[
                    invalid_mask
                ]
            )

            semantic_issues.append(
                {
                    "column": column,
                    "rule":
                        "nonnegative_integer",

                    "message": (
                        f"{column} deve essere "
                        "un conteggio intero "
                        "maggiore o uguale a zero."
                    ),

                    "invalid_count": int(
                        invalid_mask.sum()
                    ),

                    "examples": (
                        invalid_values
                        .head(20)
                        .tolist()
                    ),
                }
            )

    # --------------------------------------------------------
    # Adult population
    # --------------------------------------------------------

    if "age" in frame.columns:

        age = pd.to_numeric(
            frame["age"],
            errors="coerce",
        )

        valid_age = age[
            age.notna()
            & np.isfinite(
                age.astype(float)
            )
            ]

        underage = (
                valid_age < 18.0
        )

        if underage.any():
            semantic_issues.append(
                {
                    "column": "age",
                    "rule":
                        "adult_population",

                    "message": (
                        "La configurazione corrente "
                        "PROMETHEUS utilizza una "
                        "popolazione adulta: "
                        "age deve essere >= 18."
                    ),

                    "invalid_count": int(
                        underage.sum()
                    ),

                    "observed_min": float(
                        valid_age[
                            underage
                        ].min()
                    ),
                }
            )

    # --------------------------------------------------------
    # BMI
    # --------------------------------------------------------

    if "bmi" in frame.columns:

        bmi = pd.to_numeric(
            frame["bmi"],
            errors="coerce",
        )

        valid_bmi = bmi[
            bmi.notna()
            & np.isfinite(
                bmi.astype(float)
            )
            ]

        invalid_bmi = (
                valid_bmi <= 0.0
        )

        if invalid_bmi.any():
            semantic_issues.append(
                {
                    "column": "bmi",
                    "rule": "positive",

                    "message": (
                        "bmi deve essere "
                        "maggiore di zero."
                    ),

                    "invalid_count": int(
                        invalid_bmi.sum()
                    ),
                }
            )

    # --------------------------------------------------------
    # Days since encounter
    # --------------------------------------------------------

    if "days_since_encounter" in frame.columns:

        days = pd.to_numeric(
            frame[
                "days_since_encounter"
            ],
            errors="coerce",
        )

        valid_days = days[
            days.notna()
            & np.isfinite(
                days.astype(float)
            )
            ]

        negative_days = (
                valid_days < 0.0
        )

        if negative_days.any():
            semantic_issues.append(
                {
                    "column":
                        "days_since_encounter",

                    "rule": "nonnegative",

                    "message": (
                        "days_since_encounter "
                        "deve essere >= 0."
                    ),

                    "invalid_count": int(
                        negative_days.sum()
                    ),
                }
            )

    if semantic_issues:
        errors.append(
            {
                "code":
                    "invalid_semantic_domains",

                "message": (
                    "Sono presenti valori "
                    "incompatibili con il contratto "
                    "delle covariate PROMETHEUS."
                ),

                "columns":
                    semantic_issues,
            }
        )

    # --------------------------------------------------------
    # Reference-range warnings
    # --------------------------------------------------------

    reference_range_issues = []

    for (column, (reference_min, reference_max),) in OBSERVED_REFERENCE_RANGES.items():

        if column not in canonical_frame.columns:
            continue

        values = pd.to_numeric(
            canonical_frame[column],
            errors="coerce",
        )

        valid_values = values[
            values.notna()
            & np.isfinite(
                values.astype(float)
            )
            ]

        outside_mask = (
                (valid_values < reference_min)
                | (valid_values > reference_max)
        )

        if not outside_mask.any():
            continue

        outside = valid_values[
            outside_mask
        ]

        reference_range_issues.append(
            {
                "column": column,

                "reference_min":
                    reference_min,

                "reference_max":
                    reference_max,

                "outside_count": int(
                    outside_mask.sum()
                ),

                "observed_min": float(
                    outside.min()
                ),

                "observed_max": float(
                    outside.max()
                ),
            }
        )

    if reference_range_issues:
        warnings.append(
            {
                "code":
                    "outside_synthetic_reference_range",

                "message": (
                    "Alcuni valori sono validi "
                    "semanticamente ma ricadono "
                    "fuori dal range osservato "
                    "nella popolazione sintetica "
                    "PROMETHEUS di riferimento. "
                    "Il CSV resta utilizzabile."
                ),

                "columns":
                    reference_range_issues,
            }
        )

    # --------------------------------------------------------
    # Derived PROMETHEUS columns
    # --------------------------------------------------------

    derived_present = [
        column
        for column in DERIVED_PROMETHEUS_COLUMNS
        if column in frame.columns
    ]

    if derived_present:
        warnings.append(
            {
                "code":
                    "prometheus_derived_columns_present",
                "message": (
                    "Il CSV contiene colonne che "
                    "PROMETHEUS calcola internamente. "
                    "Non saranno considerate come "
                    "input del ranker."
                ),
                "columns": derived_present,
            }
        )

    # --------------------------------------------------------
    # Geography detection
    # --------------------------------------------------------

    municipality_column = _find_column(
        frame,
        MUNICIPALITY_ALIASES,
    )

    postal_code_column = _find_column(
        frame,
        POSTAL_CODE_ALIASES,
    )

    geography_report = {
        "municipality_column":
            municipality_column,

        "postal_code_column":
            postal_code_column,

        "real_municipality_rows": 0,

        "real_postal_code_rows": 0,

        "real_verified_rows": 0,

        "synthetic_fallback_rows": 0,

        "invalid_rows": 0,

        "ranker_input": False,
    }

    # --------------------------------------------------------
    # Geography semantic validation
    # --------------------------------------------------------

    if municipality_catalog_path is not None and postal_catalog_path is not None:

        municipality_lookup = (load_municipality_lookup(municipality_catalog_path))
        postal_lookup = (load_postal_lookup(postal_catalog_path))
        geography_errors = []

        for index, row in frame.iterrows():

            municipality_value = (
                row[municipality_column]
                if municipality_column
                else None
            )

            postal_value = (
                row[postal_code_column]
                if postal_code_column
                else None
            )

            try:
                resolved = (
                    resolve_real_residence(
                        municipality_value=(
                            municipality_value
                        ),
                        postal_code_value=(
                            postal_value
                        ),
                        municipality_lookup=(
                            municipality_lookup
                        ),
                        postal_lookup=(
                            postal_lookup
                        ),
                    )
                )

            except GeographyResolutionError as exc:

                geography_report[
                    "invalid_rows"
                ] += 1

                geography_errors.append(
                    {
                        # +2 perché il CSV:
                        # riga 1 = header.
                        "row": int(index) + 2,
                        "patient_id": (
                            _json_safe_value(
                                row.get(
                                    "patient_id"
                                )
                            )
                            if "patient_id"
                               in frame.columns
                            else None
                        ),
                        "message": str(exc),
                    }
                )

                continue

            if resolved is None:
                geography_report[
                    "synthetic_fallback_rows"
                ] += 1

                continue

            status = resolved[
                "residence_data_status"
            ]

            if status == "real_municipality":

                geography_report[
                    "real_municipality_rows"
                ] += 1

            elif status == "real_postal_code":

                geography_report[
                    "real_postal_code_rows"
                ] += 1

            elif (
                    status
                    == "real_municipality_verified_by_postal_code"
            ):

                geography_report[
                    "real_verified_rows"
                ] += 1

        if geography_errors:
            errors.append(
                {
                    "code":
                        "invalid_geography",

                    "message": (
                        "Sono presenti dati geografici "
                        "reali non risolvibili. "
                        "Non verranno sostituiti "
                        "silenziosamente con dati "
                        "simulati."
                    ),

                    "count": len(geography_errors),
                    "rows": geography_errors[:50],
                }
            )

    elif (
            municipality_column is not None
            or postal_code_column is not None
    ):

        warnings.append(
            {
                "code":"geography_not_semantically_validated",
                "message": "Colonne geografiche rilevate, ma i cataloghi geografici non sono stati forniti al validator.",
            }
        )

    identifying_normalized = {
        _normalize_header_name(column)
        for column
        in IDENTIFYING_COLUMN_ALIASES
    }

    identifying_columns = [
        str(column)
        for column in frame.columns
        if _normalize_header_name(column)
           in identifying_normalized
    ]

    if identifying_columns:
        warnings.append(
            {
                "code": "identifying_columns_present",
                "message": "Il CSV contiene colonne identificative non necessarie a PROMETHEUS. Saranno escluse dal dataset canonico prima dell'esecuzione.",
                "columns": identifying_columns,
            }
        )

    # --------------------------------------------------------
    # Unknown columns
    # --------------------------------------------------------

    known_source_columns = set(patient_column_mapping.values())
    known_source_columns.update(identifying_columns)

    for column in DERIVED_PROMETHEUS_COLUMNS:
        if column in frame.columns:
            known_source_columns.add(column)

    if municipality_column:
        known_source_columns.add(municipality_column)

    if postal_code_column:
        known_source_columns.add(postal_code_column)

    unknown_columns = [
        str(column)
        for column in frame.columns
        if column
           not in known_source_columns
    ]

    # Colonne sconosciute NON rendono
    # incompatibile il dataset.
    if unknown_columns:
        warnings.append(
            {
                "code": "extra_columns",
                "message":"Sono presenti colonne aggiuntive.Non saranno utilizzate dalla prima versione dell'adapter.",
                "columns": unknown_columns,
            }
        )

    return {
        "compatible": len(errors) == 0,
        "row_count": int(row_count),
        "required_column_count": len(REQUIRED_PATIENT_COLUMNS),
        "missing_required_columns": missing_columns,
        "geography": geography_report,
        "column_mapping": {
            canonical: source
            for canonical, source
            in patient_column_mapping.items()
        },

        "aliased_columns": [
            {
                "source": source,
                "canonical": canonical,
            }
            for canonical, source
            in patient_column_mapping.items()
            if source != canonical
        ],
        "identifying_columns": identifying_columns,
        "errors": errors,
        "warnings": warnings,
    }


__all__ = [
    "REQUIRED_PATIENT_COLUMNS",
    "NUMERIC_PATIENT_COLUMNS",
    "DERIVED_PROMETHEUS_COLUMNS",
    "MUNICIPALITY_ALIASES",
    "POSTAL_CODE_ALIASES",
    "validate_patient_csv",
]
