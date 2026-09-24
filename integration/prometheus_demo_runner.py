from __future__ import annotations

import json
import sys
import argparse
import copy
import hashlib
from pathlib import Path
from time import perf_counter
from datetime import datetime
from typing import Any
from causal_population_ranking.recommendation import (
    calibrate_and_recommend_profiles,
)

import pandas as pd
import yaml

from causal_population_ranking.dm77 import (
    DM77_LEVEL_LABELS,
    load_care_profile_catalog,
    validate_ranked_profile_comparability,
)
from causal_population_ranking.experiments import derive_experiment_seeds
from causal_population_ranking.nuisance import (
    build_profile_causal_supervision,
)
from causal_population_ranking.synthetic import (
    PROFILE_DGP_SCENARIOS,
    SYNTHETIC_POPULATION_SCENARIOS,
    generate_synthetic_population,
    generate_synthetic_profile_dgp,
)

from causal_population_ranking.ranking import (
    train_profile_rankers,
)

from causal_population_ranking.allocation import (
    allocate_recommended_profiles,
)

try:
    from .geographic_enrichment import (
        derive_geography_seed,
    )
except ImportError:
    from geographic_enrichment import (
        derive_geography_seed,
    )

try:
    # Import quando integration viene utilizzato da Flask
    from .export_stratification import (
        export_stratification_results,
        export_stratification_summary,
        export_run_metadata,
    )



except ImportError:
    # Per esecuzione diretta(da terminale): python integration/prometheus_demo_runner.py
    from export_stratification import (
        export_stratification_results,
        export_stratification_summary,
        export_run_metadata,
    )

try:
    from .Data.real_cohort_adapter import (load_real_cohort)
except ImportError:
    from Data.real_cohort_adapter import (load_real_cohort,)



class InteractiveRunNotFeasibleError(RuntimeError):
    """
    Il run interattivo è formalmente valido, ma non dispone
    di supporto empirico sufficiente per completare uno
    degli stadi scientifici PROMETHEUS.

    È distinto da un errore software.
    """

    def __init__(
        self,
        *,
        stage: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.stage = stage
        self.status = status
        self.details = details or {}

# ============================================================
# PATH DEL PROGETTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STRATIFICATION_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "outputs"
    / "stratification"
)

PROMETHEUS_ROOT = PROJECT_ROOT / "PROMETHEUS-master"

DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "integration"
    / "config"
    / "demo_config.yaml"
)

CARE_CATALOG_PATH = (
    PROMETHEUS_ROOT
    / "configs"
    / "care_catalog.yaml"
)

# Il contratto baseline need ufficialmente utilizzato
# dal repository è embedded nel pipeline.yaml originale.
BASELINE_NEED_CONTRACT_PATH = (
    PROMETHEUS_ROOT
    / "configs"
    / "pipeline.yaml"
)


# ============================================================
# CONFIG
# ============================================================

def load_demo_config(path: Path) -> dict[str, Any]:
    """Carica e valida la configurazione della demo interattiva."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Configurazione demo non trovata: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if config.get("mode") != "interactive_demo":
        raise ValueError(
            "demo_config.yaml deve avere mode: interactive_demo"
        )

    data_source = config.get("data_source", {})

    if data_source.get("type") != "synthetic":
        raise ValueError(
            "In questa prima versione è supportata "
            "solo data_source.type: synthetic"
        )

    population = config.get("population", {})

    population_size = int(population.get("size", 0))
    minimum_size = int(population.get("min_size", 100))
    maximum_size = int(population.get("max_size", 5000))

    if population_size < minimum_size:
        raise ValueError(
            f"population.size={population_size} è inferiore "
            f"al minimo configurato ({minimum_size})"
        )

    if population_size > maximum_size:
        raise ValueError(
            f"population.size={population_size} supera "
            f"il massimo UI configurato ({maximum_size})"
        )

    population_scenario = str(
        population.get("population_scenario", "")
    )

    if population_scenario not in SYNTHETIC_POPULATION_SCENARIOS:
        raise ValueError(
            f"Scenario popolazione non valido: "
            f"{population_scenario}. "
            f"Valori ammessi: "
            f"{SYNTHETIC_POPULATION_SCENARIOS}"
        )

    experiment = config.get("experiment", {})

    profile_scenario = str(
        experiment.get("scenario", "")
    )

    if profile_scenario not in PROFILE_DGP_SCENARIOS:
        raise ValueError(
            f"Scenario PROMETHEUS non valido: "
            f"{profile_scenario}. "
            f"Valori ammessi: "
            f"{PROFILE_DGP_SCENARIOS}"
        )

    baseline_mode = str(
        config.get("baseline_need", {}).get("mode", "")
    )

    if baseline_mode not in {"rules", "supervised"}:
        raise ValueError(
            "baseline_need.mode deve essere "
            "'rules' oppure 'supervised'"
        )

    return config

def load_recommendation_config() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """
    Carica dal pipeline.yaml originale:
    - calibration contract
    - recommendation contract
    - implementation settings

    In questo modo la demo riutilizza la stessa logica
    metodologica del protocollo PROMETHEUS.
    """

    with BASELINE_NEED_CONTRACT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        pipeline_config = yaml.safe_load(file) or {}

    scientific_contract = pipeline_config[
        "scientific_contract"
    ]

    calibration_contract = copy.deepcopy(
        scientific_contract[
            "calibration_contract"
        ]
    )

    recommendation_contract = copy.deepcopy(
        scientific_contract[
            "recommendation_contract"
        ]
    )

    implementation_settings = copy.deepcopy(
        pipeline_config[
            "recommendation"
        ]
    )

    return (
        calibration_contract,
        recommendation_contract,
        implementation_settings,
    )
def load_allocation_config() -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    """
    Carica dal pipeline.yaml originale il contratto
    scientifico e i parametri operativi dell'allocation.

    L'allocation avviene esclusivamente dopo il freeze
    delle raccomandazioni e può considerare soltanto
    il profilo già raccomandato.
    """

    with BASELINE_NEED_CONTRACT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        pipeline_config = yaml.safe_load(file) or {}

    allocation_contract = copy.deepcopy(
        pipeline_config[
            "scientific_contract"
        ][
            "allocation_contract"
        ]
    )

    allocation_settings = copy.deepcopy(
        pipeline_config[
            "allocation"
        ]
    )

    return (
        allocation_contract,
        allocation_settings,
    )
# ============================================================
# FUNZIONI DI STAMPA / CONTROLLO
# ============================================================

def print_separator(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def print_baseline_distribution(
    assessments: pd.DataFrame,
) -> None:
    """Stampa la distribuzione dei livelli baseline DM77."""

    counts = (
        assessments["baseline_need_level"]
        .value_counts(dropna=False)
        .sort_index()
    )

    for level in range(1, 7):

        count = int(counts.get(level, 0))

        label = DM77_LEVEL_LABELS.get(
            level,
            "Unknown",
        )

        print(
            f"Livello {level}: "
            f"{count:4d} pazienti | {label}"
        )

def load_canonical_causal_supervision_config() -> dict[str, Any]:
    """
    Carica i parametri della causal supervision direttamente
    dal pipeline.yaml originale di PROMETHEUS.

    La modalità interattiva riutilizza quindi, in questa fase,
    gli stessi parametri scientifici del protocollo canonico
    senza copiarli o modificarli.
    """

    with BASELINE_NEED_CONTRACT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        pipeline_config = yaml.safe_load(file) or {}

    causal_config = pipeline_config.get(
        "causal_supervision"
    )

    if not isinstance(causal_config, dict):
        raise ValueError(
            "Blocco causal_supervision non trovato "
            "nel pipeline.yaml originale."
        )

    return causal_config

def load_ranker_smoke_config() -> dict[str, Any]:
    """
    Costruisce una configurazione ranker leggera per
    verificare l'esecuzione end-to-end della modalità
    interattiva.

    La base proviene dal ranker canonico di PROMETHEUS.

    Gli override provengono dai baseline_ranker_settings
    già presenti nel protocollo originale sotto
    experiments.stability_diagnostics.

    Questa configurazione NON rappresenta il Full
    Experimental Protocol.
    """

    with BASELINE_NEED_CONTRACT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        pipeline_config = yaml.safe_load(file) or {}

    canonical_ranker = copy.deepcopy(
        pipeline_config["ranker"]
    )

    smoke_overrides = (
        pipeline_config[
            "experiments"
        ][
            "stability_diagnostics"
        ][
            "baseline_ranker_settings"
        ]
    )

    canonical_ranker.update(
        copy.deepcopy(smoke_overrides)
    )

    canonical_ranker["variants"] = [
        "global_rank_only"
    ]

    canonical_ranker[
        "primary_variant"
    ] = "global_rank_only"

    # Engineering-smoke compatibility:
    # global_rank_only non usa contrastive learning.
    canonical_ranker[
        "contrastive_warmup_epochs"
    ] = 0

    canonical_ranker[
        "contrastive_ramp_epochs"
    ] = 0

    canonical_ranker[
        "contrastive_final_rank_only_epochs"
    ] = 0

    canonical_ranker[
        "contrastive_minimum_active_epochs"
    ] = 0

    return canonical_ranker

def _augment_run_metadata_provenance(
    *,
    run_output_directory: Path,
    stratification_results_path: Path,
    effective_data_source: str,
    patient_data_source: str,
    causal_environment: str,
    patient_csv_upload_id: str | None,
) -> None:
    """
    Aggiunge provenance esplicita agli artifact
    dell'Interactive Application. Non modifica gli output scientifici del modello.
    """

    metadata_path = ( Path(run_output_directory) / "run_metadata.json")

    if not metadata_path.is_file():
        raise FileNotFoundError("run_metadata.json non trovato durante l'aggiornamento provenance.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    # --------------------------------------------------------
    # DATA / CAUSAL PROVENANCE
    # --------------------------------------------------------

    metadata["patient_data_source"] = patient_data_source
    metadata["causal_environment"] = causal_environment
    metadata["causal_assignment_source"] = "simulated_profile_dgp"
    metadata["causal_outcome_source"] = "simulated_profile_dgp"

    if patient_csv_upload_id is not None:
        metadata["patient_csv_upload_id"] = str(patient_csv_upload_id)

    # --------------------------------------------------------
    # SEED SEMANTICS
    # --------------------------------------------------------

    metadata["seed_usage"] = {
        "generates_patient_covariates": (effective_data_source == "synthetic"),
        "controls_semisynthetic_profile_dgp":True,
        "controls_causal_splits_and_training":True,
        "controls_posthoc_geography": ("missing_residence_only" if effective_data_source == "real_csv"else "all_patients"),
    }

    # --------------------------------------------------------
    # GEOGRAPHY PROVENANCE
    # --------------------------------------------------------

    results = pd.read_csv(stratification_results_path, encoding="utf-8-sig",)

    if "residence_data_status" in results.columns:
        status_counts = (results["residence_data_status"].value_counts(dropna=False).to_dict())
        real_statuses = {
            "real_municipality",
            "real_postal_code",
            "real_municipality_" "verified_by_postal_code",
        }

        real_rows = int(results["residence_data_status"].isin(real_statuses).sum())
        synthetic_rows = int((results["residence_data_status"] == "synthetic_posthoc_" "not_ranker_input").sum())
        existing_geography = (metadata.get("geography",{}))
        if not isinstance(existing_geography,dict,):
            existing_geography = {}

        metadata["geography"] = {
            **existing_geography,
            "ranker_input":False,
            "real_residence_rows":real_rows,
            "synthetic_residence_rows":synthetic_rows,
            "status_counts": {
                str(key): int(value)
                for key, value
                in status_counts.items()
            },
            "mode": "mixed_real_and_synthetic" if (real_rows > 0 and synthetic_rows > 0) else ( "real" if real_rows > 0 else "synthetic_posthoc"),
        }

    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================
# RUNNER INTERATTIVO - FASE 1
# ============================================================

def run_demo(
    config_path: Path,
    *,
    patients_override: int | None = None,
    seed_override: int | None = None,
    scenario_override: str | None = None,
    patient_csv_upload_id: str | None = None
) -> dict[str, str]:

    config = load_demo_config(config_path)
    config = copy.deepcopy(config)
    # ========================================================
    # GEOGRAPHY CONFIGURATION
    # ========================================================

    project_root = (Path(__file__).resolve().parents[1])
    geography_config = (config.get("geography",{},)or {})

    geography_catalog_path = None

    if geography_config.get("simulate_residence_municipality",False,):
        raw_catalog_path = (geography_config.get("municipality_catalog"))
        if not raw_catalog_path:
            raise ValueError("geography.municipality_catalog mancante nella configurazione.")

        geography_catalog_path = Path(raw_catalog_path)
        if not geography_catalog_path.is_absolute():
            geography_catalog_path = (project_root/ geography_catalog_path)

        geography_catalog_path = (geography_catalog_path.resolve() )
        if not geography_catalog_path.is_file():
            raise FileNotFoundError(f"Catalogo geografico non trovato:{geography_catalog_path}")

    if patient_csv_upload_id is not None and patients_override is not None:
        raise ValueError("patients_override e patient_csv_upload_id non possono essere utilizzati insieme.")

    if patients_override is not None:
        minimum_size = int(config["population"]["min_size"])
        maximum_size = int(config["population"]["max_size"])
        if not (minimum_size <= patients_override <= maximum_size):
            raise ValueError("patients deve essere tra {minimum_size} e {maximum_size}")
        config["population"]["size"] = (int(patients_override))

    if seed_override is not None:
        config["experiment"]["seed"] = int(seed_override)

    if scenario_override is not None:
        if scenario_override not in PROFILE_DGP_SCENARIOS:
            raise ValueError(f"Scenario PROMETHEUS non valido: {scenario_override}")
        config["experiment"]["scenario"] = (scenario_override)

    population_config = config["population"]
    experiment_config = config["experiment"]
    baseline_config = config["baseline_need"]

    population_size = int(population_config["size"])
    user_seed = int(experiment_config["seed"])
    population_scenario = str(population_config["population_scenario"])
    profile_scenario = str(experiment_config["scenario"])
    effective_data_source = str(config["data_source"]["type"])
    effective_population_scenario = population_scenario
    residence_overrides = None
    patient_data_source = "synthetic_generator"
    causal_environment = "semisynthetic_profile_dgp"

    # --------------------------------------------------------
    # 1. SEED
    print_separator("1. DERIVAZIONE SEED")
    component_seeds = derive_experiment_seeds(run_seed=user_seed)
    geography_seed = derive_geography_seed(user_seed)
    print(f"Seed utente: {user_seed}")
    print("Seed interni derivati da PROMETHEUS:")
    for name in (
        "population_seed",
        "reference_seed",
        "need_model_seed",
        "need_split_seed",
        "current_care_seed",
        "effect_seed",
        "assignment_seed",
        "outcome_seed",
    ):
        print(f"  {name}: {component_seeds[name]}")
    print(f"  geography seed: {geography_seed}")
    # --------------------------------------------------------
    # 2. CARE CATALOG
    print_separator("2. CARE PROFILE CATALOG")
    catalog = load_care_profile_catalog(CARE_CATALOG_PATH)

    # Controllo originale PROMETHEUS: verifica che i profili automatici appartengano
    # a domini causalmente comparabili.
    validate_ranked_profile_comparability(catalog)
    print(f"Catalog version: {catalog.catalog_version}")
    print(f"Profili totali: {len(catalog.profiles)}")
    print(f"Profili candidati al ranking automatico: {len(catalog.automatic_rank_profiles)}")
    for profile in catalog.profiles:
        print(
            f"  - {profile.care_profile_id} "
            f"| level={profile.care_profile_level} "
            f"| automatic_rank="
            f"{profile.automatic_rank_candidate} "
            f"| protected={profile.protected}"
        )

    # --------------------------------------------------------
    # 3. GENERAZIONE POPOLAZIONE
    if patient_csv_upload_id is not None:
        print_separator("3. CARICAMENTO COORTE CSV")
        population = load_real_cohort(patient_csv_upload_id)
        # La dimensione effettiva è SEMPRE quella realmente presente nel CSV validato.
        population_size = int(len(population.patients))
        effective_data_source = "real_csv"
        patient_data_source= "external_csv"
        effective_population_scenario = "external_patient_csv"
        # La geografia rimane separata dalle covariate utilizzate da PROMETHEUS.
        residence_overrides = (population.geography)
        print("Origine dati: real_csv")
        print(F"Upload ID: {population.upload_id}")

    else:
        print_separator("3. GENERAZIONE POPOLAZIONE")
        population = generate_synthetic_population(
            population_size=population_size,
            seed=component_seeds["population_seed"],
            history_months=int(population_config["history_months"]),
            reference_date=str(population_config["reference_date"]),
            profile=str(population_config["profile"]),
            scenario=population_scenario,
        )

    print(f"Pazienti disponibili: {len(population.patients)}")
    print(f"Record longitudinali mensili: {len(population.monthly_history)}")
    print(f"Origine dati effettiva: {effective_data_source}")
    print(f"Origine covariate patient-level: {patient_data_source}")
    print(f"Ambiente causale: {causal_environment}")
    if patient_csv_upload_id is not None:
        print("Ruolo seed sulla popolazione CSV: NON genera né modifica le covariate patient-level caricate.")
        print("Ruolo seed residuo: DGP semisintetico, split/training e fallback geografico dove necessario.")
    print(f"Scenario popolazione: {effective_population_scenario}")
    print(f"Numero covariate patient-level: {len(population.patients.columns)}")

    # --------------------------------------------------------
    # 4. PROFILE DGP
    print_separator("4. PROMETHEUS PROFILE DGP")
    result = generate_synthetic_profile_dgp(
        patients=population.patients,
        catalog=catalog,
        scenario=profile_scenario,
        need_mode=str(baseline_config["mode"]),
        reference_seed=component_seeds["reference_seed"],
        need_model_seed=component_seeds["need_model_seed"],
        need_split_seed=component_seeds["need_split_seed"],
        current_care_seed=component_seeds["current_care_seed"],
        effect_seed=component_seeds["effect_seed"],
        assignment_seed=component_seeds["assignment_seed"],
        outcome_seed=component_seeds["outcome_seed"],
        baseline_need_contract=BASELINE_NEED_CONTRACT_PATH,
        index_date=str(population_config["reference_date"]),
    )
    print(f"Scenario PROMETHEUS:{profile_scenario}")
    print(f"Dataset learner: {len(result.learner)} pazienti")

    # --------------------------------------------------------
    # 5. BASELINE NEED
    print_separator("5. BASELINE NEED - DM77 SYNTHETIC OPERATIONALIZATION")
    print_baseline_distribution(result.baseline_need_assessments)

    # --------------------------------------------------------
    # 6. CURRENT CARE
    print_separator("6. CURRENT CARE PROFILE")
    current_counts = (result.current_care_profiles["current_care_profile"].value_counts(dropna=False))
    print(current_counts.to_string())

    # --------------------------------------------------------
    # 7. ELIGIBILITY
    print_separator("7. CLINICAL ELIGIBILITY")
    eligibility = result.profile_eligibility
    eligible_rows = eligibility[eligibility["eligibility"] == True]
    discretionary_rows = eligibility[eligibility["discretionary_rank_candidate"] == True]
    print(f"Decisioni paziente-profilo valutate: {len(eligibility)}")
    print(f"Profili clinicamente eleggibili: {len(eligible_rows)}")
    print(f"Opportunità discrezionali candidate al ranking: {len(discretionary_rows)}")
    print(f"Pazienti con almeno un profilo discrezionale eleggibile:{discretionary_rows['patient_id'].nunique()}")

    # --------------------------------------------------------
    # 8. OPPORTUNITIES
    print_separator("8. PATIENT-PROFILE OPPORTUNITIES")
    opportunities = result.patient_profile_opportunities
    print(f"Numero totale opportunities: {len(opportunities)}")
    print(f"Pazienti rappresentati: {opportunities['patient_id'].nunique()}")

    if len(opportunities) > 0:
        opportunities_per_patient = (opportunities.groupby("patient_id").size())
        print(f"Media opportunities per paziente eleggibile: {opportunities_per_patient.mean():.2f}")
        print(f"Massimo opportunities per paziente:{opportunities_per_patient.max()}"
        )

    # --------------------------------------------------------
    # 9. CAUSAL SUPERVISION
    print_separator("9. CAUSAL SUPERVISION")
    causal_config = (load_canonical_causal_supervision_config())
    print("Configurazione causal supervision:")
    print(f" folds: {causal_config['folds']}")
    print(f"  repeats: {causal_config['repeats']}")
    print(f"  model: {causal_config['model']}")
    print(f"  split fractions: {causal_config['split_fractions']}")
    print()
    print("Avvio repeated cross-fitting...")

    start_time = perf_counter()

    causal_supervision = (
        build_profile_causal_supervision(
            result.learner,
            result.patient_profile_opportunities,
            causal_config,
            split_seed=component_seeds[
                "split_seed"
            ],
            nuisance_seed=component_seeds[
                "nuisance_seed"
            ],
            profile_candidates=[
                (
                    profile.care_profile_id,
                    profile.care_profile_index,
                )
                for profile
                in catalog.automatic_rank_profiles
            ],
        )
    )

    elapsed = perf_counter() - start_time

    print()
    print(
        f"Causal supervision completata "
        f"in {elapsed:.2f} secondi."
    )

    # --------------------------------------------------------
    # 10. PATIENT SPLITS
    # --------------------------------------------------------

    print_separator(
        "10. PATIENT SPLITS"
    )

    split_counts = (
        causal_supervision.patient_splits[
            "split"
        ]
        .value_counts()
    )

    print(
        split_counts.to_string()
    )

    # --------------------------------------------------------
    # 11. CAUSAL SUPERVISION SUMMARY
    # --------------------------------------------------------

    print_separator(
        "11. CAUSAL SUPERVISION SUMMARY"
    )

    audit = causal_supervision.audit

    print(
        f"Profili considerati: "
        f"{audit['profiles_considered']}"
    )

    print(
        f"Profili fitted: "
        f"{audit['profiles_fitted']}"
    )

    print(
        f"Profili con supporto empirico: "
        f"{audit['profiles_supported']}"
    )

    print(
        f"Profili senza supporto sufficiente: "
        f"{len(audit['unsupported_profiles'])}"
    )

    if audit["unsupported_profiles"]:
        print()

        print(
            "Profili unsupported:"
        )

        for profile_id in (
                audit["unsupported_profiles"]
        ):
            print(
                f"  - {profile_id}"
            )

    print()

    print(
        f"Righe causal supervision: "
        f"{len(causal_supervision.supervision)}"
    )

    opportunity_support = (
        causal_supervision.supported_opportunities
    )

    supported_count = int(
        opportunity_support[
            "empirical_support"
        ].sum()
    )

    unsupported_count = (
            len(opportunity_support)
            - supported_count
    )

    print(
        f"Opportunità annotate con supporto: "
        f"{len(opportunity_support)}"
    )

    print(
        f"Opportunità empiricamente supportate: "
        f"{supported_count}"
    )

    print(
        f"Opportunità non supportate: "
        f"{unsupported_count}"
    )

    # --------------------------------------------------------
    # 12. SUPPORT PER PROFILO
    # --------------------------------------------------------

    print_separator(
        "12. EMPIRICAL SUPPORT PER PROFILE"
    )

    support = (
        causal_supervision
        .support_diagnostics
    )

    support_summary = (
        support[
            [
                "care_profile_id",
                "profile_empirical_support",
                "profile_effective_sample_size",
                "support_status",
            ]
        ]
        .drop_duplicates(
            subset=["care_profile_id"]
        )
        .sort_values(
            "care_profile_id"
        )
    )

    print(
        support_summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # 13. RANKER - ENGINEERING SMOKE TEST
    # --------------------------------------------------------

    print_separator(
        "13. CAUSAL RANKER - ENGINEERING SMOKE TEST"
    )

    ranker_config = (
        load_ranker_smoke_config()
    )

    print(
        "Primary variant: "
        f"{ranker_config['primary_variant']}"
    )

    print(
        "Variants eseguite: "
        f"{ranker_config['variants']}"
    )

    print(
        f"Model restarts: "
        f"{ranker_config['model_restarts']}"
    )

    print(
        f"Epochs: "
        f"{ranker_config['epochs']}"
    )

    print(
        f"Training pairs: "
        f"{ranker_config['training_pairs']}"
    )

    print(
        f"Validation pairs: "
        f"{ranker_config['validation_pairs']}"
    )

    print(
        f"Contrastive sampler pairs: "
        f"{ranker_config['contrastive_pairs']}"
    )
    print(
        "Contrastive training: DISABLED "
        "(global_rank_only)"
    )

    print(
        "Contrastive schedule: "
        f"warmup={ranker_config['contrastive_warmup_epochs']}, "
        f"ramp={ranker_config['contrastive_ramp_epochs']}, "
        f"final={ranker_config['contrastive_final_rank_only_epochs']}"
    )
    print()
    print(
        "Avvio training del primary causal ranker..."
    )

    ranker_start = perf_counter()

    ranker = train_profile_rankers(
        result.learner,
        causal_supervision.supervision,
        causal_supervision.supported_opportunities,
        causal_supervision.patient_splits,
        ranker_config,
        numeric_features=causal_config[
            "numeric_features"
        ],
        categorical_features=causal_config[
            "categorical_features"
        ],
        profile_ids=[
            profile.care_profile_id
            for profile
            in catalog.automatic_rank_profiles
        ],
        model_seed=component_seeds[
            "ranker_model_seed"
        ],
        pair_seed=component_seeds[
            "ranker_pair_seed"
        ],
        validation_pair_seed=component_seeds[
            "ranker_validation_pair_seed"
        ],
        contrastive_seed=component_seeds[
            "ranker_contrastive_seed"
        ],
        gbdt_seed=component_seeds[
            "ranker_gbdt_seed"
        ],
        random_seed=component_seeds[
            "ranker_random_seed"
        ],
    )

    ranker_elapsed = (
        perf_counter() - ranker_start
    )

    print()
    print(
        f"Ranker completato in "
        f"{ranker_elapsed:.2f} secondi."
    )

    # --------------------------------------------------------
    # 14. RANKER SUMMARY
    # --------------------------------------------------------

    print_separator(
        "14. RANKER SUMMARY"
    )

    ranker_status = str(
        ranker.audit.get(
            "status",
            "unknown",
        )
    )

    primary_variant = str(
        ranker.audit.get(
            "primary_variant",
            ranker_config["primary_variant"],
        )
    )

    print(
        f"Status: {ranker_status}"
    )

    print(
        f"Primary variant: {primary_variant}"
    )

    # --------------------------------------------------------
    # Il core PROMETHEUS può correttamente decidere di NON
    # addestrare il ranker quando empirical support e split
    # non lasciano opportunità sufficienti.
    #
    # Non dobbiamo bypassare questo controllo.
    # --------------------------------------------------------

    if ranker_status != "trained":

        print()
        print(
            "RANKER NON ADDESTRATO"
        )

        print(
            "PROMETHEUS non dispone di opportunità "
            "empiricamente supportate sufficienti nei "
            "subset necessari a training/validation."
            "Questo è un esito di fattibilità scientifica, "
            "non un errore software.Le soglie di empirical support NON verranno "
            "rilassate automaticamente."
        )

        print()

        # Stampiamo eventuali diagnostiche presenti,
        # senza assumere che esistano.
        optional_audit_fields = [
            (
                "Rank-train rows",
                "rank_train_rows",
            ),
            (
                "Validation rows",
                "validation_rows",
            ),
            (
                "Opportunità supportate scored",
                "scored_supported_opportunities",
            ),
        ]

        for label, key in optional_audit_fields:

            if key in ranker.audit:
                print(
                    f"{label}: "
                    f"{ranker.audit[key]}"
                )

        raise InteractiveRunNotFeasibleError(
            stage="causal_ranker",
            status=ranker_status,
            message=(
                "Il causal ranker non può essere "
                "addestrato con il supporto empirico "
                "disponibile per questo run."
            ),
            details={
                "population_size": int(
                    population_size
                ),
                "seed": int(
                    user_seed
                ),
                "scenario": str(
                    profile_scenario
                ),
            },
        )

    # Da qui in avanti sappiamo con certezza
    # che status == trained.

    print(
        f"Rank-train rows: "
        f"{ranker.audit['rank_train_rows']}"
    )

    print(
        f"Validation rows: "
        f"{ranker.audit['validation_rows']}"
    )

    print(
        "Opportunità supportate scored: "
        f"{ranker.audit['scored_supported_opportunities']}"
    )

    primary_variant_audit = (
        ranker.audit["primary_variant_audit"]
    )

    print(
        f"Training pairs effettive: "
        f"{primary_variant_audit['train_pairs']}"
    )

    print(
        f"Validation pairs effettive: "
        f"{ranker.audit['fixed_validation_pairs']}"
    )

    scores = ranker.scores.loc[
        ranker.scores[
            "method"
        ].eq(
            ranker.audit["primary_variant"]
        )
    ].copy()

    print()

    print(
        f"Priority scores prodotti: "
        f"{len(scores)}"
    )

    if len(scores) > 0:

        priority = pd.to_numeric(
            scores["raw_priority_score"],
            errors="coerce",
        )

        print(
            "Raw priority score range: "
            f"{priority.min():.6f} "
            f"-> {priority.max():.6f}"
        )

    print()
    print(
        "NOTA: raw_priority_score è un "
        "punteggio ORDINALE di priorità."
    )

    print(
        "NON è un indice clinico di rischio "
        "e NON è ancora un beneficio calibrato."
    )

    print_separator(
        "FASE 3 COMPLETATA"
    )

    print(
        "Il primary causal ranker di PROMETHEUS "
        "è stato eseguito in configurazione "
        "engineering-smoke."
    )

    print()

    print(
        "NON abbiamo ancora eseguito:"
    )

    print(
        "- calibration;"
    )

    print(
        "- patient-level recommendation;"
    )

    print(
        "- allocation."
    )
    # --------------------------------------------------------
    # 15. CALIBRATION + PATIENT-LEVEL RECOMMENDATION
    # --------------------------------------------------------

    print_separator(
        "15. CALIBRATION + PATIENT-LEVEL RECOMMENDATION"
    )

    (
        calibration_contract,
        recommendation_contract,
        recommendation_settings,
    ) = load_recommendation_config()

    print(
        "Calibration methods: "
        f"{calibration_contract['candidate_methods']}"
    )

    print(
        "Calibration fit partitions: "
        f"{calibration_contract['fit_partitions']}"
    )

    print(
        "Minimum benefit threshold: "
        f"{recommendation_contract['primary_minimum_benefit_threshold_days']} days"
    )

    print(
        "Candidate policy: "
        f"{recommendation_contract['candidate_policy']}"
    )

    print()
    print(
        "Avvio calibrazione validation-only "
        "e costruzione raccomandazioni..."
    )

    recommendation_start = perf_counter()

    recommendation = calibrate_and_recommend_profiles(
        ranker.scores,
        causal_supervision.supervision,
        causal_supervision.supported_opportunities,
        result.baseline_need_assessments,
        result.current_care_profiles,
        causal_supervision.patient_splits,
        causal_supervision.support_diagnostics,
        primary_variant=ranker.audit[
            "primary_variant"
        ],
        calibration_contract=calibration_contract,
        recommendation_contract=recommendation_contract,
        implementation_settings=recommendation_settings,
    )

    recommendation_elapsed = (
        perf_counter() - recommendation_start
    )

    print()
    print(
        "Calibration + recommendation completata "
        f"in {recommendation_elapsed:.2f} secondi."
    )

    # --------------------------------------------------------
    # 16. CALIBRATION SUMMARY
    # --------------------------------------------------------

    print_separator(
        "16. CALIBRATION SUMMARY"
    )

    recommendation_audit = recommendation.audit

    print(
        f"Status: "
        f"{recommendation_audit['status']}"
    )

    print(
        "Metodo selezionato: "
        f"{recommendation_audit['selected_calibration_method']}"
    )

    print(
        "Righe usate per calibration: "
        f"{recommendation_audit['calibration_validation_rows']}"
    )

    print(
        "Raw score modificato: "
        f"{recommendation_audit['raw_priority_score_modified']}"
    )

    print(
        "Violazioni ordinamento raw -> calibrated: "
        f"{recommendation_audit['raw_to_calibrated_ordering_violations']}"
    )

    print(
        "Oracle usato: "
        f"{recommendation_audit['oracle_used']}"
    )

    print(
        "Capacity inputs usati: "
        f"{recommendation_audit['capacity_inputs_used']}"
    )

    # --------------------------------------------------------
    # 17. RECOMMENDATION SUMMARY
    # --------------------------------------------------------

    print_separator(
        "17. PATIENT-LEVEL RECOMMENDATION SUMMARY"
    )

    print(
        f"Pazienti totali: "
        f"{recommendation_audit['patients']}"
    )

    print(
        f"Pazienti raccomandati: "
        f"{recommendation_audit['patients_recommended']}"
    )

    print(
        f"Pazienti in abstention: "
        f"{recommendation_audit['patients_abstained']}"
    )

    print(
        f"De-intensification recommendations: "
        f"{recommendation_audit['deintensification_recommendations']}"
    )

    print()

    print(
        "Recommendation reasons:"
    )

    for reason, count in (
        recommendation_audit[
            "recommendation_reason_counts"
        ].items()
    ):
        print(
            f"  {reason}: {count}"
        )

    # --------------------------------------------------------
    # 18. RECOMMENDED LEVEL DISTRIBUTION
    # --------------------------------------------------------

    print_separator(
        "18. RECOMMENDED ACTIONABLE LEVEL"
    )

    recommendations = (
        recommendation.recommendations
    )

    recommended_counts = (
        recommendations[
            "recommended_actionable_level"
        ]
        .value_counts(dropna=False)
        .sort_index()
    )

    for level in range(1, 7):

        count = int(
            recommended_counts.get(
                level,
                0,
            )
        )

        print(
            f"Livello {level}: "
            f"{count}"
        )

    print()

    print(
        "IMPORTANTE:"
    )

    print(
        "- recommended_actionable_level NON è "
        "il baseline_need_level;"
    )

    print(
        "- in caso di abstention PROMETHEUS "
        "riporta il baseline_need_level come "
        "recommended_actionable_level;"
    )

    print(
        "- per distinguere i casi bisogna sempre "
        "leggere recommendation_abstained e "
        "recommendation_status."
    )

    # --------------------------------------------------------
    # 19. EXAMPLE RECOMMENDATIONS
    # --------------------------------------------------------

    print_separator(
        "19. ESEMPI DI RACCOMANDAZIONE"
    )

    example_columns = [
        "patient_id",
        "baseline_need_level",
        "current_care_profile_level",
        "recommended_actionable_level",
        "recommended_profile_id",
        "recommended_raw_priority_score",
        "calibrated_incremental_benefit",
        "recommendation_status",
        "recommendation_reason",
    ]

    print(
        recommendations[
            example_columns
        ]
        .head(10)
        .to_string(index=False)
    )

    print_separator(
        "FASE 4 COMPLETATA"
    )

    print(
        "Calibration e patient-level recommendation "
        "sono state completate."
    )

    print()

    print(
        "NON è stata ancora eseguita allocation."
    )
    # --------------------------------------------------------
    # 20. ALLOCATION
    # --------------------------------------------------------

    print_separator(
        "20. CAPACITY-CONSTRAINED ALLOCATION"
    )

    (
        allocation_contract,
        allocation_settings,
    ) = load_allocation_config()

    print(
        "Allocation method: "
        f"{allocation_settings['method']}"
    )

    print(
        "Candidate policy: "
        f"{allocation_contract['candidate_profiles']}"
    )

    print(
        "Alternative profile substitution allowed: "
        f"{allocation_contract['alternative_profile_substitution_allowed']}"
    )

    print(
        "Recommendation overwrite allowed: "
        f"{allocation_contract['recommendation_may_be_overwritten']}"
    )

    print(
        "Shared budget units per patient: "
        f"{allocation_settings['shared_budget_units_per_patient']}"
    )

    print(
        "Solver time limit: "
        f"{allocation_settings['solver']['time_limit_seconds']} s"
    )

    print()
    print(
        "Avvio allocation sulle raccomandazioni congelate..."
    )

    allocation_start = perf_counter()

    allocation = allocate_recommended_profiles(
        recommendation.recommendations,
        causal_supervision.supported_opportunities,
        result.resource_capacities,
        result.profile_resources,
        allocation_contract=allocation_contract,
        settings=allocation_settings,
        tie_seed=component_seeds[
            "allocator_tie_seed"
        ],
    )

    allocation_elapsed = (
        perf_counter() - allocation_start
    )

    print()
    print(
        f"Allocation completata in "
        f"{allocation_elapsed:.2f} secondi."
    )

    # --------------------------------------------------------
    # 21. ALLOCATION SUMMARY
    # --------------------------------------------------------

    print_separator(
        "21. ALLOCATION SUMMARY"
    )

    allocation_audit = allocation.audit

    print(
        f"Status: "
        f"{allocation_audit['status']}"
    )

    print(
        f"Raccomandazioni candidate: "
        f"{allocation_audit['recommended_candidates']}"
    )

    print(
        f"Raccomandazioni allocate: "
        f"{allocation_audit['allocated_recommendations']}"
    )

    print(
        f"Raccomandazioni deferred: "
        f"{allocation_audit['deferred_recommendations']}"
    )

    print(
        "Pazienti senza raccomandazione actionable: "
        f"{allocation_audit['patients_without_actionable_recommendation']}"
    )

    recommended_candidates = int(
        allocation_audit[
            "recommended_candidates"
        ]
    )

    deferred = int(
        allocation_audit[
            "deferred_recommendations"
        ]
    )

    conditional_deferral_rate = (
        deferred / recommended_candidates
        if recommended_candidates > 0
        else 0.0
    )

    print(
        "Conditional deferral rate: "
        f"{conditional_deferral_rate:.2%}"
    )

    print()

    print(
        "Shared budget limit: "
        f"{allocation_audit['shared_budget_limit']:.2f}"
    )

    print(
        "Shared budget used: "
        f"{allocation_audit['shared_budget_used']:.2f}"
    )

    print(
        "Calibrated objective value: "
        f"{allocation_audit['calibrated_objective_value']:.2f}"
    )

    print()

    print(
        f"Solver status: "
        f"{allocation_audit['solver_status']}"
    )

    print(
        "Constraint violations: "
        f"{allocation_audit['constraint_violations_total']}"
    )

    print(
        "Recommendation records modified: "
        f"{allocation_audit['recommendation_records_modified']}"
    )

    print(
        "Alternative profile substitution: "
        f"{allocation_audit['alternative_profile_substitution']}"
    )

    print(
        f"Oracle used: "
        f"{allocation_audit['oracle_used']}"
    )

    # --------------------------------------------------------
    # 22. ALLOCATION STATUS DISTRIBUTION
    # --------------------------------------------------------

    print_separator(
        "22. ALLOCATION STATUS DISTRIBUTION"
    )

    decisions = allocation.decisions

    allocation_status_counts = (
        decisions[
            "allocation_status"
        ]
        .value_counts(dropna=False)
    )

    print(
        allocation_status_counts.to_string()
    )

    # --------------------------------------------------------
    # 23. ALLOCATED CARE LEVEL DISTRIBUTION
    # --------------------------------------------------------

    print_separator(
        "23. ALLOCATED CARE LEVEL"
    )

    allocated_level_counts = (
        decisions[
            "allocated_care_level"
        ]
        .value_counts(dropna=False)
        .sort_index()
    )

    for level in range(1, 7):

        count = int(
            allocated_level_counts.get(
                level,
                0,
            )
        )

        print(
            f"Livello {level}: "
            f"{count}"
        )

    # --------------------------------------------------------
    # 24. EXAMPLE ALLOCATION DECISIONS
    # --------------------------------------------------------

    print_separator(
        "24. ESEMPI DI ALLOCATION"
    )

    allocation_columns = [
        "patient_id",
        "baseline_need_level",
        "current_care_profile_level",
        "recommended_actionable_level",
        "recommended_profile_id",
        "calibrated_incremental_benefit",
        "allocated_care_level",
        "allocated_profile_id",
        "allocation_status",
        "deferred_recommendation",
    ]

    print(
        decisions[
            allocation_columns
        ]
        .head(15)
        .to_string(index=False)
    )

    # --------------------------------------------------------
    # 25. EXPORT STRATIFICATION RESULTS
    # --------------------------------------------------------

    print_separator("25. EXPORT STRATIFICATION RESULTS")
    timestamp = datetime.now().astimezone()
    run_id = f"interactive_{timestamp.strftime('%Y%m%d_%H%M%S')}_seed{user_seed}"
    run_output_directory = (STRATIFICATION_OUTPUT_ROOT / run_id)
    print(f"Run ID: {run_id}")
    print(f"Output directory: {run_output_directory}")

    stratification_results_path = (
        export_stratification_results(
            patients=population.patients,
            baseline_need_assessments=result.baseline_need_assessments,
            allocation_decisions=allocation.decisions,
            catalog=catalog,
            output_directory=run_output_directory,
            geography_catalog_path=geography_catalog_path,
            geography_seed=geography_seed,
            residence_overrides=residence_overrides
        )
    )

    stratification_summary_path = (
        export_stratification_summary(
            stratification_results_path=stratification_results_path,
            allocation_audit=allocation.audit,
            output_directory=run_output_directory,
        )
    )

    run_metadata_path = (
        export_run_metadata(
            run_id=run_id,
            source=effective_data_source,
            population_size=population_size,
            seed=user_seed,
            population_scenario=effective_population_scenario,
            prometheus_scenario=profile_scenario,
            mode=config["mode"],
            timestamp=timestamp.isoformat(),
            dm77_status=config["metadata"]["dm77_status"],
            application_status=config["metadata"]["application_status"],
            baseline_need_mode=(baseline_config["mode"]),
            ranker_variant=(ranker.audit["primary_variant"]),
            ranker_mode="engineering_smoke",
            causal_folds=int(causal_config["folds"]),
            causal_repeats=int(causal_config["repeats"]),
            allocation_enabled=True,
            output_directory=run_output_directory,
        )
    )

    _augment_run_metadata_provenance(
        run_output_directory=run_output_directory,
        stratification_results_path=stratification_results_path,
        effective_data_source=effective_data_source,
        patient_data_source=patient_data_source,
        causal_environment=causal_environment,
        patient_csv_upload_id=patient_csv_upload_id)

    print_separator("FASE 6 COMPLETATA")
    print("Patient-level stratification export completato.")
    print()
    print(f"File: {stratification_results_path}")
    print()
    print(f"Summary: {stratification_summary_path}")
    print()
    print(f"Metadata: {run_metadata_path}")
    print()
    print("Artifact interattivi completati:")
    print("- stratification_results.csv")
    print("- stratification_summary.json")
    print("- run_metadata.json")
    return {
        "run_id": run_id,
        "output_directory": str(run_output_directory.resolve()),
        "stratification_results": str(stratification_results_path.resolve()),
        "stratification_summary": str(stratification_summary_path.resolve()),
        "run_metadata": str(run_metadata_path.resolve()),
    }

# ============================================================
# CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "PROMETHEUS Interactive Application - "
            "integration layer."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=(
            "Percorso del demo_config.yaml."
        ),
    )

    parser.add_argument(
        "--patients",
        type=int,
        default=None,
        help="Numero pazienti sintetici.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed principale del run.",
    )

    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Scenario Profile DGP PROMETHEUS.",
    )

    args = parser.parse_args()

    try:

        result = run_demo(
            args.config.resolve(),
            patients_override=args.patients,
            seed_override=args.seed,
            scenario_override=args.scenario,
        )

    except InteractiveRunNotFeasibleError as exc:

        print()
        print("=" * 70)
        print("RUN INTERATTIVO NON COMPLETABILE")
        print("=" * 70)

        print(
            f"Stage: {exc.stage}"
        )

        print(
            f"Status: {exc.status}"
        )

        print(
            f"Motivo: {exc}"
        )

        if exc.details:

            print()
            print("Dettagli:")

            for key, value in exc.details.items():
                print(
                    f"  {key}: {value}"
                )

        print()
        print(
            "Suggerimento: utilizzare una popolazione "
            "più ampia oppure un'altra configurazione "
            "scientificamente valida."
        )

        sys.exit(2)

    print()
    print("RUN RESULT")
    print(f"run_id: {result['run_id']}")
    print(
        f"output_directory: "
        f"{result['output_directory']}"
    )


if __name__ == "__main__":
    main()