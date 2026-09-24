from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import json

from causal_population_ranking.dm77 import DM77_LEVEL_LABELS
try:
    from .geographic_enrichment import (enrich_stratification_with_geography,)
except ImportError:
    from geographic_enrichment import (enrich_stratification_with_geography,)


# ============================================================
# COVARIATE LEARNER-FACING ESPORTATE
# ============================================================

PATIENT_EXPORT_COLUMNS = [
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
]


# ============================================================
# VALIDATION HELPERS
# ============================================================

def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    name: str,
) -> None:
    missing = required.difference(frame.columns)

    if missing:
        raise ValueError(
            f"{name}: colonne mancanti: "
            f"{sorted(missing)}"
        )


def _validate_unique_patients(
    frame: pd.DataFrame,
    name: str,
) -> None:
    if frame["patient_id"].astype(str).duplicated().any():
        duplicated = (
            frame.loc[
                frame["patient_id"]
                .astype(str)
                .duplicated(keep=False),
                "patient_id",
            ]
            .astype(str)
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{name}: patient_id duplicati: "
            f"{duplicated[:10]}"
        )


# ============================================================
# EXPORT
# ============================================================

def export_stratification_results(
    *,
    patients,
    baseline_need_assessments,
    allocation_decisions,
    catalog,
    output_directory,
    geography_catalog_path: Path | None = None,
    geography_seed: int | None = None,
    residence_overrides: pd.DataFrame | None = None,
) -> Path:
    """
    Costruisce il dataset patient-level finale utilizzabile
    dalla dashboard aggiungendo:
    - covariate patient-level;
    - label descrittive;
    - nomi dei care profile;
    - baseline explanation;
    - ordinamento delle colonne.
    """

    output_directory = Path(output_directory)

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 1. CONTROLLI INPUT
    # --------------------------------------------------------

    _require_columns(patients,{"patient_id"},"patients",)
    _require_columns(
        baseline_need_assessments,
        {
            "patient_id",
            "baseline_need_level",
            "baseline_need_explanation",
            "baseline_need_status",
            "baseline_need_protected_pathway",
        },
        "baseline_need_assessments",
    )

    _require_columns(
        allocation_decisions,
        {
            "patient_id",
            "split",
            "baseline_need_level",
            "current_care_profile",
            "current_care_profile_level",
            "recommended_actionable_level",
            "recommended_profile_id",
            "recommended_raw_priority_score",
            "calibrated_incremental_benefit",
            "recommendation_abstained",
            "recommendation_status",
            "recommendation_reason",
            "allocated_profile_id",
            "allocated_care_level",
            "allocation_status",
            "allocation_reason",
            "deferred_recommendation",
        },
        "allocation_decisions",
    )

    _validate_unique_patients(
        patients,
        "patients",
    )

    _validate_unique_patients(
        baseline_need_assessments,
        "baseline_need_assessments",
    )

    _validate_unique_patients(
        allocation_decisions,
        "allocation_decisions",
    )

    # --------------------------------------------------------
    # 2. COVARIATE PAZIENTE
    # --------------------------------------------------------

    available_patient_columns = [
        column
        for column in PATIENT_EXPORT_COLUMNS
        if column in patients.columns
    ]

    patient_frame = patients[
        available_patient_columns
    ].copy()

    patient_frame["patient_id"] = (
        patient_frame["patient_id"].astype(str)
    )

    # --------------------------------------------------------
    # 3. DECISIONI PROMETHEUS
    # --------------------------------------------------------

    decision_columns = [
        "patient_id",
        "split",
        "baseline_need_level",
        "current_care_profile",
        "current_care_profile_level",
        "recommended_actionable_level",
        "recommended_profile_id",
        "recommended_raw_priority_score",
        "calibrated_incremental_benefit",
        "recommendation_abstained",
        "recommendation_status",
        "recommendation_reason",
        "selected_profile_effective_sample_size",
        "selected_patient_empirical_support",
        "selected_profile_positive_validation_evidence",
        "benefit_margin_over_threshold_days",
        "allocated_profile_id",
        "allocated_care_level",
        "allocation_status",
        "allocation_reason",
        "deferred_recommendation",
        "allocated_calibrated_benefit",
        "allocated_incremental_resource_cost",
    ]

    # Alcune colonne diagnostiche potrebbero cambiare
    # tra versioni; manteniamo soltanto quelle presenti.
    available_decision_columns = [
        column
        for column in decision_columns
        if column in allocation_decisions.columns
    ]

    decisions = allocation_decisions[
        available_decision_columns
    ].copy()

    decisions["patient_id"] = (
        decisions["patient_id"].astype(str)
    )

    # --------------------------------------------------------
    # 4. BASELINE NEED EXPLANATION
    # --------------------------------------------------------

    baseline_details = (
        baseline_need_assessments[
            [
                "patient_id",
                "baseline_need_explanation",
                "baseline_need_status",
                "baseline_need_protected_pathway",
            ]
        ]
        .copy()
    )

    baseline_details["patient_id"] = (
        baseline_details["patient_id"].astype(str)
    )

    # --------------------------------------------------------
    # 5. MERGE PATIENT-LEVEL
    # --------------------------------------------------------

    results = patient_frame.merge(
        decisions,
        on="patient_id",
        how="inner",
        validate="one_to_one",
    )

    results = results.merge(
        baseline_details,
        on="patient_id",
        how="left",
        validate="one_to_one",
    )

    # Nessun paziente deve essere perso durante l'export.
    if len(results) != len(patients):
        raise ValueError(
            "Export incompleto: "
            f"patients={len(patients)}, "
            f"results={len(results)}"
        )

    # --------------------------------------------------------
    # 6. LABEL DM77
    # --------------------------------------------------------

    results["baseline_need_label"] = (
        results["baseline_need_level"]
        .map(DM77_LEVEL_LABELS)
    )

    results["recommended_actionable_label"] = (
        results["recommended_actionable_level"]
        .map(DM77_LEVEL_LABELS)
    )

    results["allocated_care_label"] = (
        results["allocated_care_level"]
        .map(DM77_LEVEL_LABELS)
    )

    # --------------------------------------------------------
    # 7. CARE PROFILE NAMES
    # --------------------------------------------------------

    profile_name_by_id = {
        profile.care_profile_id:
            profile.care_profile_name
        for profile in catalog.profiles
    }

    results["current_care_profile_name"] = (
        results["current_care_profile"]
        .map(profile_name_by_id)
    )

    results["recommended_profile_name"] = (
        results["recommended_profile_id"]
        .map(profile_name_by_id)
    )

    results["allocated_profile_name"] = (
        results["allocated_profile_id"]
        .map(profile_name_by_id)
    )

    # --------------------------------------------------------
    # 8. CONTROLLI DI COERENZA
    # --------------------------------------------------------

    _validate_unique_patients(
        results,
        "stratification_results",
    )

    # recommended + abstained deve coprire tutta
    # la popolazione.
    if results["recommendation_abstained"].isna().any():
        raise ValueError(
            "recommendation_abstained contiene valori mancanti"
        )

    if results["deferred_recommendation"].isna().any():
        raise ValueError(
            "deferred_recommendation contiene valori mancanti"
        )

    recommendation_abstained = (
        results["recommendation_abstained"]
        .astype(bool)
    )

    # Una raccomandazione deferred deve necessariamente
    # avere avuto una raccomandazione actionable.
    invalid_deferred = (
        results["deferred_recommendation"]
        .astype(bool)
        & results["recommendation_abstained"]
        .astype(bool)
    )

    if invalid_deferred.any():
        raise ValueError(
            "Incoerenza: esistono pazienti deferred "
            "senza raccomandazione actionable."
        )

    # --------------------------------------------------------
    # 9. ORDINE COLONNE PER DASHBOARD
    # --------------------------------------------------------

    preferred_order = [
        # Identificativo
        "patient_id",

        # Covariate principali
        "age",
        "female",
        "condition_distinct",
        "prior_inpatient",
        "prior_emergency",
        "medication_distinct",
        "frailty_index",
        "functional_limitation_score",
        "social_fragility_score",
        "cognitive_impairment",
        "non_self_sufficiency",
        "caregiver_available",
        "housing_instability",
        "palliative_need",

        # Altre covariate learner-facing
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
        "recent_utilization_trend",
        "multimorbidity",
        "polypharmacy",
        "encounter_count",
        "days_since_encounter",
        "procedure_count",
        "careplan_count",

        # Split sperimentale
        "split",

        # Baseline need
        "baseline_need_level",
        "baseline_need_label",
        "baseline_need_explanation",
        "baseline_need_status",
        "baseline_need_protected_pathway",

        # Current care
        "current_care_profile",
        "current_care_profile_name",
        "current_care_profile_level",

        # Recommendation
        "recommended_profile_id",
        "recommended_profile_name",
        "recommended_actionable_level",
        "recommended_actionable_label",
        "recommended_raw_priority_score",
        "calibrated_incremental_benefit",
        "recommendation_status",
        "recommendation_reason",
        "recommendation_abstained",

        # Support / confidence diagnostics
        "selected_patient_empirical_support",
        "selected_profile_effective_sample_size",
        "selected_profile_positive_validation_evidence",
        "benefit_margin_over_threshold_days",

        # Allocation
        "allocated_profile_id",
        "allocated_profile_name",
        "allocated_care_level",
        "allocated_care_label",
        "allocation_status",
        "allocation_reason",
        "deferred_recommendation",
        "allocated_calibrated_benefit",
        "allocated_incremental_resource_cost",
    ]

    ordered_columns = [
        column
        for column in preferred_order
        if column in results.columns
    ]

    remaining_columns = [
        column
        for column in results.columns
        if column not in ordered_columns
    ]

    results = results[
        ordered_columns + remaining_columns
    ]

    results = results.sort_values(
        "patient_id",
        kind="stable",
    ).reset_index(drop=True)

    # ========================================================
    # OPTIONAL POST-HOC GEOGRAPHIC ENRICHMENT
    # ========================================================

    if geography_catalog_path is not None:

        if geography_seed is None:
            raise ValueError(
                "geography_seed è obbligatorio "
                "quando l'enrichment geografico è attivo."
            )

        results = (
            enrich_stratification_with_geography(
                results=results,
                catalog_path=geography_catalog_path,
                seed=geography_seed,
                residence_overrides=residence_overrides
            )
        )

    # --------------------------------------------------------
    # 10. SAVE
    # --------------------------------------------------------

    output_path = (
        output_directory
        / "stratification_results.csv"
    )

    results.to_csv(
        output_path,
        index=False,

        # UTF-8 BOM:
        # rende più semplice l'apertura in Excel/Windows
        # mantenendo correttamente gli accenti.
        encoding="utf-8-sig",
    )

    print(
        f"stratification_results.csv salvato: "
        f"{output_path.resolve()}"
    )

    print(
        f"Righe esportate: {len(results)}"
    )

    print(
        f"Colonne esportate: {len(results.columns)}"
    )

    return output_path

def _boolean_series(
    series: pd.Series,
    column_name: str,
) -> pd.Series:
    """
    Converte in modo controllato una colonna booleana.

    Supporta sia veri bool pandas sia valori testuali
    letti nuovamente da CSV ("True"/"False").
    """

    if series.isna().any():
        raise ValueError(
            f"{column_name} contiene valori mancanti"
        )

    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)

    normalized = (
        series
        .astype("string")
        .str.strip()
        .str.lower()
    )

    valid = normalized.isin(
        ["true", "false"]
    )

    if not valid.all():
        invalid_values = (
            series.loc[~valid]
            .astype(str)
            .unique()
            .tolist()
        )

        raise ValueError(
            f"{column_name}: valori booleani non validi: "
            f"{invalid_values[:10]}"
        )

    return normalized.eq("true")


def _level_distribution(series: pd.Series,) -> dict[str, int]:
    """
    Restituisce sempre i livelli 1..6, anche quando
    un livello non è presente nel run.
    """

    numeric = pd.to_numeric(series, errors="coerce",)
    return {
        str(level): int(numeric.eq(level).sum())
        for level in range(1, 7)
    }

try:
    from .geographic_enrichment import (
        enrich_stratification_with_geography,
    )

except ImportError:

    from geographic_enrichment import (
        enrich_stratification_with_geography,
    )


def export_stratification_summary(
    *,
    stratification_results_path: Path,
    allocation_audit: dict[str, Any],
    output_directory: Path,
) -> Path:
    """
    Produce KPI aggregati patient-level per la dashboard.

    IMPORTANTE
    ----------
    Le metriche non vengono usate per modificare le
    decisioni PROMETHEUS: sono esclusivamente reporting.
    """

    output_directory = Path(
        output_directory
    )

    results = pd.read_csv(
        stratification_results_path,
        encoding="utf-8-sig",
    )

    if results.empty:
        raise ValueError(
            "Impossibile creare il summary: "
            "stratification_results.csv è vuoto."
        )

    patient_count = len(results)

    recommendation_abstained = (
        _boolean_series(
            results["recommendation_abstained"],
            "recommendation_abstained",
        )
    )

    deferred = _boolean_series(
        results["deferred_recommendation"],
        "deferred_recommendation",
    )

    recommended = (
        results["recommendation_status"]
        .astype(str)
        .eq("recommended")
    )

    # Distribuzione dei livelli SOLO tra i pazienti che hanno ricevuto una vera raccomandazione.
    recommended_only_level_distribution = (
        _level_distribution(
            results.loc[
                recommended,
                "recommended_actionable_level",
            ]
        )
    )

    current_level = pd.to_numeric(
        results["current_care_profile_level"],
        errors="coerce",
    )

    recommended_level = pd.to_numeric(
        results["recommended_actionable_level"],
        errors="coerce",
    )

    # Intensification:
    # esiste una vera raccomandazione actionable
    # e il livello raccomandato è superiore
    # al current care level.
    intensification = (
        recommended
        & recommended_level.gt(current_level)
    )

    # Azione allo stesso livello:
    # può comunque essere un cambio di care profile
    # all'interno dello stesso livello DM77.
    same_level_action = (
        recommended
        & recommended_level.eq(current_level)
    )

    # Maintenance:
    # usiamo la semantica esplicita del core:
    # il profilo migliore supportato non supera
    # la minimum-benefit threshold.
    maintenance = (
        results["recommendation_reason"]
        .astype(str)
        .eq(
            "BENEFIT_NOT_STRICTLY_ABOVE_THRESHOLD"
        )
    )

    allocated = (
        results["allocation_status"]
        .astype(str)
        .eq(
            "allocated_recommended_profile"
        )
    )

    no_actionable = (
        results["allocation_status"]
        .astype(str)
        .eq(
            "no_actionable_recommendation"
        )
    )

    recommended_count = int(
        recommended.sum()
    )

    abstained_count = int(
        recommendation_abstained.sum()
    )

    intensification_count = int(
        intensification.sum()
    )

    same_level_action_count = int(
        same_level_action.sum()
    )

    maintenance_count = int(
        maintenance.sum()
    )

    allocated_count = int(
        allocated.sum()
    )

    deferred_count = int(
        deferred.sum()
    )

    no_actionable_count = int(
        no_actionable.sum()
    )

    # --------------------------------------------------------
    # BASELINE -> RECOMMENDED MATRIX
    # --------------------------------------------------------

    matrix = pd.crosstab(
        results["baseline_need_level"],
        results["recommended_actionable_level"],
    )

    baseline_to_recommended = {}

    for baseline_level in range(1, 7):

        row = {}

        for recommended_level_value in range(1, 7):

            value = 0

            if (
                baseline_level in matrix.index
                and recommended_level_value
                in matrix.columns
            ):
                value = int(
                    matrix.loc[
                        baseline_level,
                        recommended_level_value,
                    ]
                )

            row[str(recommended_level_value)] = (
                value
            )

        baseline_to_recommended[
            str(baseline_level)
        ] = row

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = {
        "patient_count": int(patient_count),

        "baseline_level_distribution": (
            _level_distribution(
                results["baseline_need_level"]
            )
        ),

        "recommended_level_distribution": (
            _level_distribution(
                results[
                    "recommended_actionable_level"
                ]
            )
        ),

        "recommended_only_level_distribution": (
            recommended_only_level_distribution
        ),

        "allocated_level_distribution": (
            _level_distribution(
                results["allocated_care_level"]
            )
        ),

        "recommendation": {
            "recommended_count": (
                recommended_count
            ),
            "recommendation_rate": (
                recommended_count
                / patient_count
            ),

            "abstained_count": (
                abstained_count
            ),
            "abstention_rate": (
                abstained_count
                / patient_count
            ),

            "intensification_count": (
                intensification_count
            ),
            "intensification_rate": (
                intensification_count
                / patient_count
            ),

            "same_level_action_count": (
                same_level_action_count
            ),
            "same_level_action_rate": (
                same_level_action_count
                / patient_count
            ),

            "maintenance_count": (
                maintenance_count
            ),
            "maintenance_rate": (
                maintenance_count
                / patient_count
            ),

            "maintenance_definition": (
                "recommendation_reason == "
                "BENEFIT_NOT_STRICTLY_ABOVE_THRESHOLD"
            ),

            "recommendation_reason_counts": {
                str(key): int(value)
                for key, value
                in results[
                    "recommendation_reason"
                ]
                .value_counts(dropna=False)
                .items()
            },
        },

        "allocation": {
            "recommended_candidates": (
                recommended_count
            ),

            "allocated_count": (
                allocated_count
            ),

            "deferred_count": (
                deferred_count
            ),

            "no_actionable_recommendation_count": (
                no_actionable_count
            ),

            "allocation_rate_among_recommended": (
                allocated_count
                / recommended_count
                if recommended_count > 0
                else 0.0
            ),

            "conditional_deferral_rate": (
                deferred_count
                / recommended_count
                if recommended_count > 0
                else 0.0
            ),

            "shared_budget_limit": float(
                allocation_audit[
                    "shared_budget_limit"
                ]
            ),

            "shared_budget_used": float(
                allocation_audit[
                    "shared_budget_used"
                ]
            ),

            "calibrated_objective_value": float(
                allocation_audit[
                    "calibrated_objective_value"
                ]
            ),

            "constraint_violations": int(
                allocation_audit[
                    "constraint_violations_total"
                ]
            ),
        },

        "baseline_to_recommended_matrix": (
            baseline_to_recommended
        ),

        "interpretation_notes": {
            "baseline_need_level": (
                "Descrive bisogno e complessità."
            ),

            "recommended_actionable_level": (
                "Deriva dal profilo supportato "
                "raccomandato. Nei casi di abstention "
                "il core può riportare il baseline level."
            ),

            "allocated_care_level": (
                "Rappresenta il care level realmente "
                "attivabile dopo i vincoli operativi."
            ),

            "raw_priority_score": (
                "Punteggio ordinale di priorità; "
                "non indice clinico di rischio."
            ),
        },
    }

    output_path = (
        output_directory
        / "stratification_summary.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    print(
        "stratification_summary.json salvato: "
        f"{output_path.resolve()}"
    )

    return output_path

def export_run_metadata(
    *,
    run_id: str,
    source: str,
    population_size: int,
    seed: int,
    population_scenario: str,
    prometheus_scenario: str,
    mode: str,
    timestamp: str,
    dm77_status: str,
    application_status: str,
    baseline_need_mode: str,
    ranker_variant: str,
    ranker_mode: str,
    causal_folds: int,
    causal_repeats: int,
    allocation_enabled: bool,
    output_directory: Path,
) -> Path:
    """
    Salva i metadati riproducibili del run interattivo.

    Questo file descrive configurazione e provenienza
    dell'esecuzione; non contiene decisioni patient-level.
    """

    output_directory = Path(output_directory)

    metadata = {
        "run_id": str(run_id),

        "source": str(source),

        "population_size": int(population_size),

        "seed": int(seed),

        "population_scenario": str(
            population_scenario
        ),

        "scenario": str(
            prometheus_scenario
        ),

        "mode": str(mode),

        "timestamp": str(timestamp),

        "dm77_status": str(dm77_status),

        "application_status": str(
            application_status
        ),

        "baseline_need_mode": str(
            baseline_need_mode
        ),

        "causal_supervision": {
            "folds": int(causal_folds),
            "repeats": int(causal_repeats),
        },

        "ranker": {
            "variant": str(ranker_variant),

            "execution_mode": str(
                ranker_mode
            ),
        },

        "allocation_enabled": bool(
            allocation_enabled
        ),

        "scientific_interpretation": {
            "dm77": (
                "synthetic methodological "
                "operationalization; not official "
                "DM77 thresholds"
            ),

            "raw_priority_score": (
                "ordinal priority score; "
                "not a clinical risk score"
            ),

            "recommendation": (
                "supported model-based actionable "
                "care recommendation"
            ),

            "allocation": (
                "resource-constrained activation "
                "after recommendation freeze"
            ),
        },
    }

    output_path = (
        output_directory
        / "run_metadata.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    print(
        "run_metadata.json salvato: "
        f"{output_path.resolve()}"
    )

    return output_path