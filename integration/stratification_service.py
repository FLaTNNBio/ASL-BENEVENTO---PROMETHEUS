from __future__ import annotations

import json
import math
import re

import pandas as pd
import unicodedata
from pathlib import Path
from typing import Any

from .prometheus_demo_runner import (
    InteractiveRunNotFeasibleError,
    PROFILE_DGP_SCENARIOS,
    run_demo,
)

from .Data.csv_upload_service import (
    PatientCsvUploadError,
    resolve_staged_patient_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEMO_CONFIG_PATH = (
        PROJECT_ROOT
        / "integration"
        / "config"
        / "demo_config.yaml"
)

STRATIFICATION_OUTPUT_ROOT = (
        PROJECT_ROOT
        / "outputs"
        / "stratification"
)

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


BENEVENTO_BOUNDARIES_PATH = (
    PROJECT_ROOT
    / "integration"
    / "Data"
    / "Geography"
    / "benevento_municipalities_2026.geojson"
)

RUN_ID_PATTERN = re.compile(
    r"^interactive_\d{8}_\d{6}_seed\d+$"
)


# ============================================================
# EXCEPTIONS
# ============================================================

class StratificationRequestValidationError(ValueError):
    """
    La richiesta ricevuta contiene parametri sintatticamente o semanticamente non validi.
    In Flask verrà tradotta in HTTP 400.
    """

    def __init__(self, message: str, *, field: str | None = None, ) -> None:
        super().__init__(message)
        self.field = field


class StratificationRunNotFoundError(FileNotFoundError):
    """
    Il run richiesto non esiste nell'output directory - Viene tradotto come errore 404
    """

    def __init__(self, run_id: str, ) -> None:
        super().__init__(f"Run di stratificazione non trovato: {run_id}")
        self.run_id = run_id


class StratificationGeographyUnavailableError(RuntimeError):
    """
    Il run esiste, ma non contiene ancora
    l'enrichment geografico richiesto.
    """
    pass

class StratificationBoundaryDataUnavailableError(RuntimeError):
    """
    I risultati del run sono disponibili,
    ma il layer dei confini amministrativi
    necessario alla mappa non è disponibile.
    """

    pass


# ============================================================
# VALIDATION
# ============================================================

def _parse_integer(value: Any, *, field: str, ) -> int:
    """
    Converte in intero un parametro proveniente da JSON.
    """

    if isinstance(value, bool):
        raise StratificationRequestValidationError(f"{field} deve essere un numero intero.",field=field)

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise StratificationRequestValidationError(f"{field} deve essere un numero intero.", field=field) from exc

    return parsed


def validate_stratification_request(payload: Any, ) -> dict[str, Any]:
    """
    Valida e normalizza il payload dell'InteractiveApplication.
    Payload previsto:
    {
        "patients": 1000,
        "seed": 42,
        "scenario": "baseline_identifiable"
    }
    """

    if not isinstance(payload, dict):
        raise StratificationRequestValidationError("Il body della richiesta deve essere un oggetto JSON.")

    # Patients
    # Sono consentite due modalità mutuamente esclusive:
    # 1. synthetic:patients
    # 2. real_csv:patient_csv_upload_id
    # Il numero di pazienti di un CSV NON può essere imposto
    # dalla request: deriva esclusivamente dal file validato.

    raw_patients = payload.get("patients")
    raw_upload_id = payload.get("patient_csv_upload_id")
    has_patients = raw_patients is not None and str(raw_patients).strip() != ""
    has_upload_id = raw_upload_id is not None and str(raw_upload_id).strip() != ""

    if has_patients and has_upload_id:
        raise StratificationRequestValidationError("Specificare una sola sorgente dati: patients per la popolazione sintetica oppure patient_csv_upload_id per un CSV validato.", field="data_source")

    if not has_patients and not has_upload_id:
        raise StratificationRequestValidationError("È necessario specificare patients oppure patient_csv_upload_id.", field="data_source")

    # SYNTHETIC
    if has_patients:
        patients = _parse_integer(raw_patients,field="patients")
        if not 100 <= patients <= 5000:
            raise StratificationRequestValidationError("patients deve essere compreso tra 100 e 5000.", field="patients")
        patient_csv_upload_id = None
        data_source = "synthetic"

    # REAL CSV
    else:
        patients = None
        patient_csv_upload_id = str(raw_upload_id).strip().lower()

        try:
            # Validiamo anche che l'upload esista realmente
            # nello staging e non sia un ID arbitrario.
            resolve_staged_patient_csv(patient_csv_upload_id)

        except PatientCsvUploadError as exc:
            raise StratificationRequestValidationError(str(exc), field="patient_csv_upload_id") from exc
        data_source = "real_csv"

    # Seed
    seed = _parse_integer(payload.get("seed", 42, ), field="seed", )

    if seed < 0:
        raise StratificationRequestValidationError("seed deve essere maggiore o uguale a 0.", field="seed", )

    # Scenario
    scenario = payload.get("scenario", "baseline_identifiable", )

    if not isinstance(scenario, str, ):
        raise StratificationRequestValidationError("scenario deve essere una stringa.", field="scenario", )
    scenario = scenario.strip()

    if scenario not in PROFILE_DGP_SCENARIOS:
        raise StratificationRequestValidationError("Scenario PROMETHEUS non valido: "f"{scenario}", field="scenario", )

    return {
        "data_source": data_source,
        "patients": patients,
        "patient_csv_upload_id": patient_csv_upload_id,
        "seed": seed,
        "scenario": scenario,
    }


def _resolve_run_directory(run_id: str, ) -> Path:
    """
    Valida il run_id e restituisce la directory associata.
    """

    if not isinstance(run_id, str):
        raise StratificationRequestValidationError("run_id deve essere una stringa.", field="run_id", )

    run_id = run_id.strip()

    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise StratificationRequestValidationError("Formato run_id non valido.", field="run_id", )

    output_root = (STRATIFICATION_OUTPUT_ROOT.resolve())
    run_directory = (STRATIFICATION_OUTPUT_ROOT / run_id).resolve()

    # Sicurezza aggiuntiva: il run deve essere
    # figlio diretto della directory stratification.
    if run_directory.parent != output_root:
        raise StratificationRequestValidationError("run_id non valido.", field="run_id", )

    if not run_directory.is_dir():
        raise StratificationRunNotFoundError(run_id)

    return run_directory


#======================================================
#HELPER
#====================================================
def _normalize_municipality_name(value: object,) -> str:
    """
    Normalizza il nome del comune esclusivamente  ai fini del join tra risultati sintetici e confini amministrativi ISTAT.
    Il nome originale non viene modificato
    negli artifact.
    """

    if value is None:
        return ""

    text = unicodedata.normalize("NFKC",str(value),)
    text = (text.replace("’", "'").replace("`", "'").strip().casefold())

    # Elimina eventuali spazi multipli.
    return " ".join(text.split())


# APPLICATION SERVICE
def run_stratification_request(payload: Any, ) -> dict[str, Any]:
    """
    Responsabilità:
    1. validare l'input web;
    2. invocare la modalità Interactive PROMETHEUS;
    3. restituire un risultato JSON-friendly.
    """

    request = validate_stratification_request(payload)
    result = run_demo(DEMO_CONFIG_PATH, patients_override=request["patients"], seed_override=request["seed"],
                      scenario_override=request["scenario"], patient_csv_upload_id=(request["patient_csv_upload_id"]))

    return {
        "status": "completed",
        "run_id": result["run_id"],
        "request": {
            "data_source": request["data_source"],
            "patient_csv_upload_id": request["patient_csv_upload_id"],
            "patients": request["patients"],
            "seed": request["seed"],
            "scenario": request["scenario"],
        },

        "artifacts": {
            "stratification_results": ("stratification_results.csv"),
            "stratification_summary": ("stratification_summary.json"),
            "run_metadata": ("run_metadata.json"),
        },
    }


def get_stratification_results(
        *,
        run_id: str,
        page: Any = 1,
        page_size: Any = 25,
        search: Any = None,
        baseline_level: Any = None,
        recommendation_status: Any = None,
        allocation_status: Any = None,
        sort_by: Any = "patient_id",
        sort_direction: Any = "asc",
        municipality: Any = None,
) -> dict[str, Any]:
    """
    Legge gli artifact di un run PROMETHEUS già completato.
    Restituisce:
    - stratification summary;
    - run metadata;
    - pagina patient-level del CSV;
    - informazioni di paginazione.
    """

    run_directory = _resolve_run_directory(run_id)

    # --------------------------------------------------------
    # Pagination validation
    # --------------------------------------------------------
    page = _parse_integer(page, field="page", )
    page_size = _parse_integer(page_size, field="page_size", )
    if page < 1:
        raise StratificationRequestValidationError("page deve essere maggiore o uguale a 1.", field="page", )
    if not 1 <= page_size <= 100:
        raise StratificationRequestValidationError("page_size deve essere compreso tra 1 e 100.", field="page_size", )

    # --------------------------------------------------------
    # FILTER VALIDATION
    # --------------------------------------------------------

    search = (str(search).strip()
              if search is not None
              else ""
              )

    if len(search) > 100:
        raise StratificationRequestValidationError("La ricerca non può superare 100 caratteri.", field="search", )

    parsed_baseline_level = None

    if baseline_level is not None and str(baseline_level).strip() != "":
        parsed_baseline_level = _parse_integer(baseline_level, field="baseline_level", )

        if not 1 <= parsed_baseline_level <= 6:
            raise StratificationRequestValidationError("baseline_level deve essere compreso tra 1 e 6.",
                                                       field="baseline_level", )

    allowed_recommendation_statuses = {"recommended", "abstained"}

    recommendation_status = (str(recommendation_status).strip()
                             if recommendation_status is not None
                             else ""
                             )

    if (
            recommendation_status
            and recommendation_status
            not in allowed_recommendation_statuses
    ):
        raise StratificationRequestValidationError(
            "recommendation_status non valido.",
            field="recommendation_status",
        )

    allowed_allocation_statuses = {
        "allocated_recommended_profile",
        "deferred_recommended_profile",
        "no_actionable_recommendation",
    }

    allocation_status = (
        str(allocation_status).strip()
        if allocation_status is not None
        else ""
    )

    if (
            allocation_status
            and allocation_status
            not in allowed_allocation_statuses
    ):
        raise StratificationRequestValidationError(
            "allocation_status non valido.",
            field="allocation_status",
        )
    municipality = (
        str(municipality).strip()
        if municipality is not None
        else ""
    )

    if len(municipality) > 150:
        raise StratificationRequestValidationError(
            "Il nome del comune non può superare 150 caratteri.",
            field="municipality",
        )

    # --------------------------------------------------------
    # SORT VALIDATION
    # --------------------------------------------------------

    allowed_sort_columns = {
        "patient_id",
        "age",
        "baseline_need_level",
        "current_care_profile_level",
        "recommended_actionable_level",
        "calibrated_incremental_benefit",
        "recommendation_status",
        "allocated_care_level",
        "allocation_status",
        "residence_municipality",
    }

    sort_by = str(
        sort_by or "patient_id"
    ).strip()

    if sort_by not in allowed_sort_columns:
        raise StratificationRequestValidationError(
            "Campo di ordinamento non valido.",
            field="sort_by",
        )

    sort_direction = str(
        sort_direction or "asc"
    ).strip().lower()

    if sort_direction not in {
        "asc",
        "desc",
    }:
        raise StratificationRequestValidationError("sort_direction deve essere asc oppure desc.",
                                                   field="sort_direction", )

    # --------------------------------------------------------
    # Artifact paths
    # --------------------------------------------------------

    results_path = (
            run_directory
            / "stratification_results.csv"
    )

    summary_path = (
            run_directory
            / "stratification_summary.json"
    )

    metadata_path = (
            run_directory
            / "run_metadata.json"
    )

    required_artifacts = [
        results_path,
        summary_path,
        metadata_path,
    ]

    missing_artifacts = [
        path.name
        for path in required_artifacts
        if not path.is_file()
    ]

    if missing_artifacts:
        raise RuntimeError(
            "Run incompleto. Artifact mancanti: "
            f"{missing_artifacts}"
        )

    # --------------------------------------------------------
    # JSON artifacts
    # --------------------------------------------------------

    with summary_path.open(
            "r",
            encoding="utf-8",
    ) as file:
        summary = json.load(file)

    with metadata_path.open(
            "r",
            encoding="utf-8",
    ) as file:
        metadata = json.load(file)

    # --------------------------------------------------------
    # Patient-level results
    # --------------------------------------------------------

    results = pd.read_csv(
        results_path,
        encoding="utf-8-sig",
    )

    results = pd.read_csv(
        results_path,
        encoding="utf-8-sig",
    )

    total_rows = len(results)

    filtered_results = results.copy()

    # --------------------------------------------------------
    # PATIENT SEARCH
    # --------------------------------------------------------

    if search:
        filtered_results = (
            filtered_results.loc[
                filtered_results[
                    "patient_id"
                ]
                .astype(str)
                .str.contains(
                    search,
                    case=False,
                    regex=False,
                    na=False,
                )
            ]
        )

    # --------------------------------------------------------
    # BASELINE NEED LEVEL
    # --------------------------------------------------------

    if parsed_baseline_level is not None:
        baseline_numeric = pd.to_numeric(
            filtered_results[
                "baseline_need_level"
            ],
            errors="coerce",
        )

        filtered_results = (
            filtered_results.loc[
                baseline_numeric.eq(
                    parsed_baseline_level
                )
            ]
        )

    # --------------------------------------------------------
    # RECOMMENDATION STATUS
    # --------------------------------------------------------

    if recommendation_status:
        filtered_results = (
            filtered_results.loc[
                filtered_results[
                    "recommendation_status"
                ]
                .astype(str)
                .eq(
                    recommendation_status
                )
            ]
        )

    # --------------------------------------------------------
    # ALLOCATION STATUS
    # --------------------------------------------------------

    if allocation_status:
        filtered_results = (
            filtered_results.loc[
                filtered_results[
                    "allocation_status"
                ]
                .astype(str)
                .eq(
                    allocation_status
                )
            ]
        )

    # --------------------------------------------------------
    # GLOBAL SORT
    # --------------------------------------------------------

    filtered_results = (
        filtered_results
        .sort_values(
            by=sort_by,
            ascending=(
                    sort_direction == "asc"
            ),
            na_position="last",
            kind="stable",
        )
    )

    # --------------------------------------------------------
    # RESIDENCE MUNICIPALITY
    # --------------------------------------------------------

    if municipality:

        if (
            "residence_municipality"
            not in filtered_results.columns
        ):
            raise StratificationRequestValidationError(
                "Il run non contiene informazioni "
                "geografiche utilizzabili.",
                field="municipality",
            )

        municipality_values = (
            filtered_results[
                "residence_municipality"
            ]
            .astype(str)
            .str.strip()
            .str.casefold()
        )

        filtered_results = (
            filtered_results.loc[
                municipality_values.eq(
                    municipality.casefold()
                )
            ]
        )

    filtered_rows = len(filtered_results)

    total_pages = max(
        1,
        math.ceil(
            filtered_rows / page_size
        ),
    )

    if page > total_pages:
        raise StratificationRequestValidationError(
            f"page {page} non disponibile. "
            f"Il run contiene {total_pages} pagine.",
            field="page",
        )

    start = (
                    page - 1
            ) * page_size

    end = min(
        start + page_size,
        total_rows,
    )

    page_frame = (
        filtered_results
        .iloc[start:end]
        .copy()
    )

    # to_json converte correttamente anche
    # NaN pandas -> JSON null.
    rows = json.loads(
        page_frame.to_json(
            orient="records"
        )
    )

    return {
        "status": "completed",

        "run_id": run_id,

        "summary": summary,

        "metadata": metadata,

        "pagination": {
            "page": page,
            "page_size": page_size,

            # Popolazione complessiva del run
            "total_rows": total_rows,

            # Pazienti che rispettano i filtri
            "filtered_rows": filtered_rows,

            "total_pages": total_pages,
            "returned_rows": len(rows),
        },

        "filters": {
            "search": search or None,
            "baseline_level": parsed_baseline_level,
            "recommendation_status": (recommendation_status or None),
            "allocation_status": (allocation_status or None),
            "sorting": {
                "sort_by": sort_by,
                "sort_direction": sort_direction,
            },
            "municipality": municipality or None,
        },

        "columns": (
            results.columns.tolist()
        ),

        "rows": rows,
    }


def get_stratification_geography(*, run_id: str, ) -> dict[str, Any]:
    """
    Restituisce un'aggregazione geografica post-hoc
    dei risultati PROMETHEUS. N.B. non partecipa al ranking causale.
    """
    # ------------------ RUN DIRECTORY-------------------

    run_directory = _resolve_run_directory(run_id)
    results_path = (run_directory / "stratification_results.csv")
    metadata_path = (run_directory / "run_metadata.json")

    if not results_path.is_file():
        raise StratificationRunNotFoundError(
            f"Risultati non trovati per il run "
            f"{run_id}."
        )

    # ----------- LOAD RESULTS----------------
    results = pd.read_csv(results_path, encoding="utf-8-sig", )

    # --------------- GEOGRAPHY VALIDATION

    required_geography_columns = {
        "residence_municipality",
        "residence_latitude",
        "residence_longitude",
        "residence_data_status",
    }
    missing_geography_columns = (required_geography_columns - set(results.columns))
    if missing_geography_columns:
        raise StratificationGeographyUnavailableError(
            "Questo run non contiene dati geografici. "
            "Eseguire una nuova stratificazione con "
            "l'enrichment geografico abilitato."
        )

    required_decision_columns = {
        "patient_id",
        "baseline_need_level",
        "recommendation_status",
        "allocation_status",
    }

    missing_decision_columns = (required_decision_columns - set(results.columns))

    if missing_decision_columns:
        raise RuntimeError(
            "Il file dei risultati non contiene "
            "tutte le colonne decisionali necessarie: "
            + ", ".join(
                sorted(
                    missing_decision_columns
                )
            )
        )

    # ------- CLEAN GEOGRAPHIC ROWS-------

    frame = results.copy()

    frame["residence_municipality"] = (
        frame["residence_municipality"]
        .astype(str)
        .str.strip()
    )

    frame["residence_latitude"] = pd.to_numeric(frame["residence_latitude"], errors="coerce", )
    frame["residence_longitude"] = pd.to_numeric(frame["residence_longitude"], errors="coerce", )
    frame["baseline_need_level"] = pd.to_numeric(frame["baseline_need_level"], errors="coerce", )
    frame = frame.loc[frame["residence_municipality"].ne("") & frame["residence_latitude"].notna() & frame[
        "residence_longitude"].notna()].copy()

    if frame.empty:
        raise StratificationGeographyUnavailableError(
            "Il run contiene colonne geografiche, "
            "ma nessun paziente dispone di una "
            "localizzazione valida."
        )

    # -----------OPTIONAL PROVINCE
    if "residence_province" not in frame.columns:
        frame["residence_province"] = None

    # ---------------- AGGREGATION

    municipalities: list[dict[str, Any]] = []
    frame["_municipality_key"] = (frame["residence_municipality"].map(_normalize_municipality_name))
    frame = frame.loc[frame["_municipality_key"].ne("")].copy()
    grouped = frame.groupby("_municipality_key",sort=True,dropna=False,)
    for municipality_key, group in grouped:

        # CANONICAL DISPLAY NAME
        municipality_names = (group["residence_municipality"].dropna().astype(str).str.strip())
        if municipality_names.empty:
            municipality = (municipality_key)

        else:
            municipality = (municipality_names.value_counts().index[0])

        patient_count = int(len(group))

        # RECOMMENDATION
        recommendation_status = (group["recommendation_status"].astype(str))
        recommended_count = int(recommendation_status.eq("recommended").sum())
        abstained_count = int(recommendation_status.eq("abstained").sum())

        # ALLOCATION
        allocation_status = (group["allocation_status"].astype(str))
        allocated_count = int(allocation_status.eq("allocated_recommended_profile").sum())
        deferred_count = int(allocation_status.eq("deferred_recommended_profile").sum())
        no_actionable_count = int(allocation_status.eq("no_actionable_recommendation").sum())

        # BASELINE NEED
        baseline_levels = pd.to_numeric(group["baseline_need_level"], errors="coerce", )
        mean_baseline_need = (
            float(baseline_levels.mean())
            if baseline_levels.notna().any()
            else None
        )
        baseline_distribution = {str(level): int(baseline_levels.eq(level).sum())
                                 for level in range(1, 7, )
                                 }

        # RATES
        recommendation_rate = (
            recommended_count
            / patient_count
            if patient_count
            else 0.0
        )

        allocated_rate = (
            allocated_count
            / recommended_count
            if recommended_count
            else 0.0
        )

        deferred_rate = (
            deferred_count
            / recommended_count
            if recommended_count
            else 0.0
        )

        # ----------------------------------------------------
        # LOCATION
        # ----------------------------------------------------
        latitude = float(group["residence_latitude"].median())
        longitude = float(group["residence_longitude"].median())
        province_values = (group["residence_province"].dropna().astype(str).str.strip())
        province = (
            province_values.iloc[0]
            if not province_values.empty
            else None
        )

        # RECORD
        municipalities.append(
            {
                "municipality": str(municipality),
                "province": province,
                "latitude": latitude,
                "longitude": longitude,
                "patient_count": (patient_count),
                "mean_baseline_need": (mean_baseline_need),
                "recommended_count": (recommended_count),
                "abstained_count": (abstained_count),
                "allocated_count": (allocated_count),
                "deferred_count": (deferred_count),
                "no_actionable_count": (no_actionable_count),
                "recommendation_rate": (recommendation_rate),
                # Percentuale tra i pazienti
                # realmente raccomandati.
                "allocated_rate_among_recommended": (allocated_rate),
                "deferred_rate_among_recommended": (deferred_rate),
                "baseline_level_distribution": (baseline_distribution),
            }
        )

    # GLOBAL VALIDATION

    aggregated_patient_count = sum(
        municipality[
            "patient_count"
        ]
        for municipality
        in municipalities
    )

    if aggregated_patient_count != len(frame):
        raise RuntimeError(
            "Errore nell'aggregazione geografica: "
            "il numero di pazienti aggregati "
            "non coincide con il numero di pazienti "
            "localizzati."
        )

    # ========================================================
    # METADATA
    # ========================================================

    run_metadata = {}

    if metadata_path.is_file():

        try:

            with metadata_path.open(
                    "r",
                    encoding="utf-8",
            ) as handle:

                run_metadata = json.load(
                    handle
                )

        except Exception:

            # I risultati geografici restano utilizzabili
            # anche se il metadata non è leggibile.
            run_metadata = {}

    geography_metadata = (
        run_metadata.get(
            "geography",
            {}
        )
        if isinstance(
            run_metadata,
            dict,
        )
        else {}
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {
        "status": "completed",

        "run_id": run_id,

        "geography": {
            "data_status": (
                "synthetic_posthoc_not_ranker_input"
            ),

            "ranker_input": False,

            "municipality_count": int(
                len(municipalities)
            ),

            "localized_patients": int(
                len(frame)
            ),

            "total_patients": int(
                len(results)
            ),

            "metadata": (
                geography_metadata
            ),
        },

        "municipalities": municipalities,
    }


def get_stratification_geography_geojson(*, run_id: str,) -> dict[str, Any]:
    """
    Costruisce una FeatureCollection GeoJSON
    unendo:
    - confini amministrativi ISTAT;
    - aggregazione geografica post-hoc
      dei risultati PROMETHEUS.
    I poligoni non partecipano in alcun modo
    al ranking o alla recommendation.
    """

    #AGGREGAZIONE PROMETHEUS
    geography_result = (get_stratification_geography(run_id=run_id,))
    municipality_results = (geography_result.get("municipalities",[],))


    #LOAD ISTAT GEOJSON
    if not BENEVENTO_BOUNDARIES_PATH.is_file():
        raise (
            StratificationBoundaryDataUnavailableError("Layer dei confini comunali ISTAT non disponibile.")
        )

    try:
        with BENEVENTO_BOUNDARIES_PATH.open("r",encoding="utf-8",) as handle:
            boundaries = json.load(handle)
    except Exception as exc:
        raise (
            StratificationBoundaryDataUnavailableError("Impossibile leggere il layer dei confini comunali ISTAT.")
        ) from exc

    if boundaries.get("type") != "FeatureCollection":
        raise (
            StratificationBoundaryDataUnavailableError("Il layer ISTAT non è una FeatureCollection GeoJSON valida.")
        )

    features = boundaries.get("features",[])
    if not features:
        raise (
            StratificationBoundaryDataUnavailableError("Il layer ISTAT non contiene comuni.")
        )

    # INDEX PROMETHEUS RESULTS BY MUNICIPALITY
    result_by_municipality = {}
    for municipality in municipality_results:
        normalized_name = ( _normalize_municipality_name(municipality.get( "municipality")))

        if not normalized_name:
            continue
        # Dopo l'aggregazione normalizzata,ogni comune deve comparire una sola volta.
        if (normalized_name in result_by_municipality):
            raise RuntimeError(
                "Aggregazione geografica non univoca per il comune normalizzato "f"{normalized_name!r}."
            )

        result_by_municipality[normalized_name] = municipality

    # JOIN ISTAT -> PROMETHEUS
    enriched_features = []
    matched_names = set()
    unmatched_boundaries = []
    for feature in features:
        properties = dict(feature.get("properties", {}) or {})
        municipality_name = (properties.get("municipality"))
        normalized_name = (_normalize_municipality_name(municipality_name))
        metrics = (result_by_municipality.get(normalized_name))

        # Comune con pazienti nel run
        if metrics is not None:
            matched_names.add(normalized_name)
            properties.update(
                {
                    "patient_count": metrics.get("patient_count", 0,),
                    "mean_baseline_need": metrics.get("mean_baseline_need"),
                    "recommended_count": metrics.get("recommended_count", 0,),
                    "abstained_count": metrics.get("abstained_count", 0,),
                    "allocated_count": metrics.get("allocated_count", 0,),
                    "deferred_count": metrics.get("deferred_count", 0,),
                    "no_actionable_count": metrics.get("no_actionable_count",0,),
                    "recommendation_rate": metrics.get("recommendation_rate",0.0,),
                    "allocated_rate_among_recommended": metrics.get("allocated_rate_among_recommended", 0.0,),
                    "deferred_rate_among_recommended":metrics.get("deferred_rate_among_recommended", 0.0,),
                    "baseline_level_distribution":metrics.get("baseline_level_distribution",{},),
                    "has_population_data": True,
                }
            )

        # Comune ISTAT senza pazienti assegnati
        else:
            unmatched_boundaries.append(municipality_name)
            properties.update(
                {
                    "patient_count": 0,
                    "mean_baseline_need": None,
                    "recommended_count": 0,
                    "abstained_count": 0,
                    "allocated_count": 0,
                    "deferred_count": 0,
                    "no_actionable_count": 0,
                    "recommendation_rate":0.0,
                    "allocated_rate_among_recommended":0.0,
                    "deferred_rate_among_recommended":0.0,
                    "baseline_level_distribution":
                        {
                            str(level): 0
                            for level
                            in range(
                                1,
                                7,
                            )
                        },

                    "has_population_data":
                        False,
                }
            )


        enriched_features.append(
            {
                "type": "Feature",

                "properties":
                    properties,

                "geometry":
                    feature.get(
                        "geometry"
                    ),
            }
        )


    # ========================================================
    # 5. FIND RESULT MUNICIPALITIES WITHOUT ISTAT POLYGON
    # ========================================================

    unmatched_results = []


    for municipality in municipality_results:

        municipality_name = (
            municipality.get(
                "municipality"
            )
        )


        normalized_name = (
            _normalize_municipality_name(
                municipality_name
            )
        )


        if (
            normalized_name
            not in matched_names
        ):

            unmatched_results.append(
                municipality_name
            )


    # ========================================================
    # 6. JOIN VALIDATION
    # ========================================================

    joined_patient_count = sum(

        int(
            feature[
                "properties"
            ].get(
                "patient_count",
                0,
            )
            or 0
        )

        for feature
        in enriched_features
    )


    expected_patient_count = int(
        geography_result[
            "geography"
        ].get(
            "localized_patients",
            0,
        )
    )


    if (
        joined_patient_count
        != expected_patient_count
    ):

        raise RuntimeError(
            "Il join territoriale ha perso "
            "o duplicato pazienti: "
            f"attesi={expected_patient_count}, "
            f"aggregati={joined_patient_count}."
        )


    # ========================================================
    # 7. RESPONSE GEOJSON
    # ========================================================

    return {
        "type": "FeatureCollection",
        # Foreign members consentiti dal formato GeoJSON.
        "run_id": run_id,
        "geography": {
            **geography_result.get("geography", {}),
            "boundary_source": "ISTAT_2026_generalized",
            "boundary_crs": "EPSG:4326",
            "boundary_count": len(enriched_features),
            "matched_municipality_count": len(matched_names),
            "unmatched_result_municipalities": unmatched_results,
            "municipalities_without_patients": unmatched_boundaries,
            "joined_patient_count": joined_patient_count,
            "ranker_input": False,
        },
        "features": enriched_features,
    }

# Riesportiamo l'eccezione scientifica in modo che
# server.py possa gestirla senza conoscere il runner.
__all__ = [
    "InteractiveRunNotFeasibleError",
    "StratificationRequestValidationError",
    "StratificationRunNotFoundError",
    "run_stratification_request",
    "validate_stratification_request",
    "get_stratification_results",
    "StratificationGeographyUnavailableError",
    "get_stratification_geography",
    "StratificationBoundaryDataUnavailableError",
    "get_stratification_geography_geojson",
]
