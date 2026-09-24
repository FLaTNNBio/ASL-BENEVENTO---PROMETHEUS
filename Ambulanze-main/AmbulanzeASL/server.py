import sys
from pathlib import Path
from flask import Flask, request, jsonify, redirect, send_from_directory, send_file, render_template
import allocator_cp_sat as alloc
import shlex
import subprocess
import json
import re
import shutil

import sys
import os
from pathlib import Path

from datetime import datetime


# ============================================================
# PROGETTO ROOT / INTEGRATION LAYER
# ============================================================

def _find_project_root() -> Path:
    """
    La root attesa contiene:
        - integration/
        - PROMETHEUS-master/
        - Ambulanze-main/
    """

    current_file = Path(__file__).resolve()

    for parent in current_file.parents:

        if (
                (parent / "integration").is_dir()
                and
                (parent / "PROMETHEUS-master").is_dir()
        ):
            return parent

    raise RuntimeError(
        "Impossibile individuare la root del progetto "
        "contenente integration/ e PROMETHEUS-master/."
    )


PROJECT_ROOT = _find_project_root()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from integration.stratification_service import (
    InteractiveRunNotFeasibleError,
    StratificationRequestValidationError,
    StratificationRunNotFoundError,
    get_stratification_results,
    run_stratification_request,
    StratificationGeographyUnavailableError,
    get_stratification_geography,
    StratificationBoundaryDataUnavailableError,
    get_stratification_geography_geojson,
)

from integration.asl_assistant_service import (
    ASLAssistantRequestError,
    ASLAssistantInterpretationError,
    ASLAssistantLLMUnavailableError,
    interpret_asl_assistant_request,
    validate_asl_assistant_request,
)

from integration.ph_118_severity_service import (
    ALLOWED_METRICS as PH_118_ALLOWED_METRICS,
    PH118SeverityError,
    preview_ph_118_severity,
    materialize_ph_118_scenario,
)

from integration.run_118_summary_service import (
    Run118SummaryError,
    build_118_run_summary,
    compare_118_run_summaries,
    get_118_run_summary_semantics,
    build_118_resource_allocation
)

from integration.run_118_explain_payload import (
    Run118ExplainPayloadError,
    build_118_llm_payload,
)

from integration.run_118_explain_llm import (
    Run118ExplainLLMError,
    Run118ExplainLLMUnavailableError,
    explain_118_payload,
)

from integration.Data.csv_upload_service import (
    MAX_UPLOAD_BYTES,
    PatientCsvUploadError,
    validate_and_stage_patient_csv,
)

from integration.Data.compatibility_report import (
    write_patient_csv_template,
)

# Path base del progetto (cartella di server.py + index.html)
BASE_DIR = Path(__file__).resolve().parent
SCRIPT = BASE_DIR / "allocator_cp_sat.py"

# # ✅ DATA DIR di default (assoluto, su disco)
# DEFAULT_DATA_DIR = Path(r"C:\Users\martina\Desktop\PROGETTO\Ambulanze-main\AmbulanzeASL\dataset\data")
#
# # ✅ Cartelle su disco per servire dataset e runs
# DATA_DIR_FS = DEFAULT_DATA_DIR
# RUNS_DIR_FS = Path(r"C:\Users\martina\Desktop\PROGETTO\Ambulanze-main\AmbulanzeASL\runs")


DEFAULT_DATA_DIR = (BASE_DIR / "dataset" / "data").resolve()
DATA_DIR_FS = DEFAULT_DATA_DIR
RUNS_DIR_FS = (BASE_DIR / "runs").resolve()

# Scenari territoriali prodotti dall'integrazione
# Population Health -> 118.
PH_118_SCENARIOS_DIR = (PROJECT_ROOT / "outputs" / "118_scenarios").resolve()

# Path per upload CSV
PATIENT_CSV_TEMPLATE_PATH = (Path(__file__).resolve().parents[2] / "templates" / "patient_dataset_template.csv")

# ✅ Mount web (URL) per dataset e runs
DATA_MOUNT = "/dataset/data"
RUNS_MOUNT = "/runs"

# Una sola app, con static configurato alla cartella del progetto
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")


def _which_py():
    return sys.executable


def _allocator_subprocess_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False


def preflight(base: Path):
    """Controlla i file minimi richiesti dal solver. Ritorna (ok, missing:list, demand_used:str|None)."""
    missing = []
    must = [base / "comuni.csv", base / "od_time_min.csv"]
    for m in must:
        if not _exists(m):
            missing.append(str(m))

    demA = base / "weighted_demand_by_comune_code.csv"
    demB = base / "demand_by_comune_code.csv"
    has_demand = _exists(demA) or _exists(demB)
    if not has_demand:
        missing.append(f"{demA} OR {demB}")

    has_sites = any([
        _exists(base / "sites.csv"),
        _exists(base / "presidi_attuali.csv"),
        _exists(base / "sites_geocoded.csv"),
    ])
    if not has_sites:
        missing.append(
            f"{base / 'sites.csv'} OR ({base / 'presidi_attuali.csv'}[, {base / 'presidi_potenziali.csv'}]) OR {base / 'sites_geocoded.csv'}"
        )

    demand_used = str(demA if _exists(demA) else (demB if _exists(demB) else "")) or None
    return (len(missing) == 0, missing, demand_used)


def has_flag(flag: str) -> bool:
    try:
        r = subprocess.run([_which_py(), str(SCRIPT), "-h"],
                           cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=_allocator_subprocess_env())
        h = (r.stdout or "") + "\n" + (r.stderr or "")
        return flag in h
    except Exception:
        return False


# ============================================================
# SEVERITÀ TERRITORIALE 118
# ============================================================

ALLOWED_SEVERITY_SOURCES = {
    "original",
    "population_health",
}

SCENARIO_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+$"
)

RUN_118_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+$"
)


def _resolve_118_run_dir(run_id: str) -> Path:
    """
    Risolve in modo sicuro una directory di run 118.
    Sono ammessi esclusivamente run presenti sotto
    AmbulanzeASL/runs.
    Il browser non può fornire path arbitrari.
    """
    run_id = str(run_id or "").strip()
    if not run_id:
        raise ValueError("run_id obbligatorio.")

    if not RUN_118_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id non valido.")

    run_dir = (RUNS_DIR_FS / run_id).resolve()

    # Protezione path traversal.
    if not run_dir.is_relative_to(RUNS_DIR_FS):
        raise ValueError("run_id non valido.")

    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run 118 non trovato: {run_id}")

    return run_dir


def _resolve_ph_118_scenario(scenario_id: str, ) -> Path:
    """
    Risolve in modo sicuro uno scenario PH -> 118.
    """
    scenario_id = str(scenario_id or "").strip()

    if not scenario_id:
        raise ValueError("severity_scenario_id obbligatorio quando severity_source=population_health.")

    if not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
        raise ValueError("severity_scenario_id non valido.")

    scenario_dir = (PH_118_SCENARIOS_DIR / scenario_id).resolve()

    # Protezione path traversal.
    if not scenario_dir.is_relative_to(PH_118_SCENARIOS_DIR):
        raise ValueError("Scenario Population Health non valido.")

    if not scenario_dir.is_dir():
        raise FileNotFoundError(f"Scenario Population Health non trovato: {scenario_id}")

    return scenario_dir


def _resolve_118_demand_for_source(severity_source: str, severity_scenario_id: str | None = None, ):
    """
    Restituisce il file di domanda che la mappa 118 deve usare.
    La logica replica quella dell'allocator:
    - original: preferisce weighted_demand_by_comune_code.csv con fallback a demand_by_comune_code.csv;
    - population_health: usa esclusivamente il weighted demand dello scenario PH confermato.
    """

    severity_source = str(severity_source or "original").strip().lower()
    if severity_source not in ALLOWED_SEVERITY_SOURCES:
        raise ValueError("severity_source deve essere 'original' oppure 'population_health'.")

    # --------------------------------------------------------
    # ORIGINAL
    # --------------------------------------------------------
    if severity_source == "original":
        weighted_path = (DEFAULT_DATA_DIR / "weighted_demand_by_comune_code.csv")
        raw_path = (DEFAULT_DATA_DIR / "demand_by_comune_code.csv")

        if weighted_path.exists():
            return weighted_path, {
                "severity_source": "original",
                "severity_scenario_id": None,
                "source_run_id": None,
                "indicator": None,
                "demand_kind": "weighted",
            }

        if raw_path.exists():
            return raw_path, {
                "severity_source": "original",
                "severity_scenario_id": None,
                "source_run_id": None,
                "indicator": None,
                "demand_kind": "raw",
            }

        raise FileNotFoundError("Nessun file di domanda 118 disponibile nel dataset originale.")

    # --------------------------------------------------------
    # POPULATION HEALTH
    # --------------------------------------------------------
    scenario_id = str(severity_scenario_id or "").strip()
    scenario_dir = _resolve_ph_118_scenario(scenario_id)
    weighted_path = (scenario_dir / "weighted_demand_by_comune_code.csv")
    metadata_path = (scenario_dir / "severity_metadata.json")
    if not weighted_path.exists():
        raise FileNotFoundError("Lo scenario Population Health non contiene weighted_demand_by_comune_code.csv.")

    if not metadata_path.exists():
        raise FileNotFoundError("Lo scenario Population Health non contiene severity_metadata.json.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("severity_source") != "population_health":
        raise ValueError("Metadata dello scenario Population Health non coerenti.")

    return weighted_path, {
        "severity_source": "population_health",
        "severity_scenario_id": scenario_id,
        "source_run_id": metadata.get("source_run_id"),
        "indicator": metadata.get("metric"),
        "demand_kind": "weighted",
    }


def prepare_effective_data_dir(payload: dict, out_dir: Path, ):
    """
    Determina quale severità territoriale usare.
    ORIGINAL: Utilizza direttamente dataset/data originale.
    POPULATION HEALTH: Crea una copia run-specific del dataset originale
    e sostituisce solo weighted_demand_by_comune_code.csv con quello prodotto dallo scenario Population Health.
    Il dataset originale non viene mai modificato.
    """

    severity_source = str(payload.get("severity_source", "original", )).strip().lower()
    if severity_source not in ALLOWED_SEVERITY_SOURCES:
        raise ValueError("severity_source deve essere 'original' oppure 'population_health' ")

    out_dir.mkdir(parents=True, exist_ok=True, )

    # ---------------MODALITÀ ORIGINALE
    if severity_source == "original":
        weighted_path = (DEFAULT_DATA_DIR / "weighted_demand_by_comune_code.csv")
        metadata = {
            "severity_source": "original",
            "severity_scenario_id": None,
            "source_run_id": None,
            "indicator": None,
            "effective_data_dir": str(DEFAULT_DATA_DIR),
            "weighted_demand_source": (
                str(weighted_path)
                if weighted_path.exists()
                else None
            ),
        }

        (out_dir / "run_input_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, ),
                                                         encoding="utf-8", )

        return DEFAULT_DATA_DIR, metadata

    # ------------MODALITA POPULATION HEALTH

    scenario_id = str(payload.get("severity_scenario_id", "")).strip()
    scenario_dir = _resolve_ph_118_scenario(scenario_id)
    scenario_weighted = scenario_dir / "weighted_demand_by_comune_code.csv"
    scenario_metadata_path = (scenario_dir / "severity_metadata.json")

    if not scenario_weighted.exists():
        raise FileNotFoundError("Lo scenario Population Health non contiene weighted_demand_by_comune_code.csv.")

    if not scenario_metadata_path.exists():
        raise FileNotFoundError("Lo scenario Population Health non contiene severity_metadata.json.")

    scenario_metadata = json.loads(scenario_metadata_path.read_text(encoding="utf-8"))

    if scenario_metadata.get("severity_source") != "population_health":
        raise ValueError("Metadata scenario incoerenti: severity_source non è 'population_health'.")

    # Dataset effettivo specifico del run.
    effective_data_dir = out_dir / "input_data"

    if effective_data_dir.exists():
        shutil.rmtree(effective_data_dir)

    shutil.copytree(DEFAULT_DATA_DIR, effective_data_dir, )

    # Sostituisco SOLO la domanda pesata.
    shutil.copy2(scenario_weighted, effective_data_dir / "weighted_demand_by_comune_code.csv", )

    metadata = {
        "severity_source": "population_health",
        "severity_scenario_id": scenario_id,
        "source_run_id": (scenario_metadata.get("source_run_id")),
        "indicator": (scenario_metadata.get("metric")),
        "method": (scenario_metadata.get("method")),
        "effective_data_dir": str(effective_data_dir),
        "weighted_demand_source": str(scenario_weighted),
        "original_dataset_dir": str(DEFAULT_DATA_DIR),
    }

    (out_dir / "run_input_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, ),
                                                     encoding="utf-8", )
    return effective_data_dir, metadata


def build_cmd(p: dict):
    args = [_which_py(), str(SCRIPT)]

    # OUT DIR (auto se vuoto) → path assoluto su disco
    out_dir = p.get("out_dir")
    if not out_dir:
        out_dir = BASE_DIR / "runs" / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = (BASE_DIR / out_dir).resolve()
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    # args.extend(["--out-dir", str(out_dir)])
    data_dir, severity_metadata = (prepare_effective_data_dir(p, out_dir, ))
    args.extend(["--data-dir", str(data_dir.resolve()), ])
    args.extend(["--out-dir", str(out_dir.resolve()), ])

    # Helper per parametri stringa
    def add(k, v):
        if v is None:
            return
        s = str(v).strip()
        if not s:
            return
        args.extend([f"--{k}", s])

    # Parametri standard
    add("T", p.get("T"))
    add("type-speed", p.get("type_speed"))
    add("purchase-costs", p.get("purchase_costs"))
    add("opex-costs", p.get("opex_costs"))
    add("bases", p.get("bases"))
    add("limit-bases", p.get("limit_bases"))
    add("full-coverage", p.get("full_coverage"))
    add("doctor-codes", p.get("doctor_codes"))
    # add("doctor-cover", "strict")
    doctor_cover = str(p.get("doctor_cover") or "strict").strip().lower()

    if doctor_cover not in {"off", "strict", "feasible-only", }:
        raise ValueError(f"doctor_cover non valido: {doctor_cover}")
    add("doctor-cover", doctor_cover, )
    # staff-per-type / doctors-per-type (compat)
    staff = p.get("staff_per_type")
    if staff:
        if has_flag("--staff-per-type"):
            add("staff-per-type", staff)
        else:
            add("doctors-per-type", staff)
    # Medici (budget + modalità)
    if p.get("doctors_total"): add("doctors-total", p.get("doctors_total"))
    if has_flag("--doctors-budget-mode"): add("doctors-budget-mode", p.get("doctors_budget_mode"))
    if has_flag("--reloc-psaut"): add("reloc-psaut", p.get("reloc_psaut"))

    add("psaut-min", p.get("psaut_min"))
    add("psaut-exact", p.get("psaut_exact"))
    add("threads", p.get("threads"))
    add("time-limit-sec", p.get("time_limit_sec"))

    if has_flag("--relax-weights"):
        add("relax-weights", p.get("relax_weights"))

    # # turnoff famiglie con medico (se supportato dal solver)
    # if has_flag("--turnoff-doctor-families"):
    #     val = p.get("turnoff_doctor_families")
    #     if val in ("on", "off"):
    #         args.extend(["--turnoff-doctor-families", val])

    # ✅ NUOVO: Budget economico (CAPEX+OPEX) e modalità ambito
    #   - dal frontend puoi inviare: budget_total (numero) e budget_mode:
    #       * 'capex'        → mappo a 'purchase' (solo acquistabili)
    #       * 'capex_opex'   → mappo a 'all'      (tutti gli slot attivi)
    #       * oppure direttamente 'purchase' / 'all'
    bt = p.get("budget_total")

    if bt not in (None, "",): add("budget-total", bt, )
    bm_in = p.get("budget_mode")
    # === NUOVO: infermieri & coupling AUTO_MED
    if has_flag("--nurses-per-type"):
        add("nurses-per-type", p.get("nurses_per_type"))
    if has_flag("--nurses-total"):
        add("nurses-total", p.get("nurses_total"))
    if has_flag("--nurse-unit-opex"):
        add("nurse-unit-opex", p.get("nurse_unit_opex"))

    # ... già inoltri nurses e auto-med-transport ...
    if has_flag("--auto-med-transport"):
        add("auto-med-transport", p.get("auto_med_transport"))

    # NUOVO: ritardo trasporto (min)
    if has_flag("--auto-transport-delay"):
        add("auto-transport-delay", p.get("auto_transport_delay"))

    # if has_flag("--budget-mode") and bm_in not in (None, "",):
    #     m = str(bm_in).strip().lower()
    #     if m in ("capex", "purchase"):
    #         add("budget-mode", "purchase")
    #     elif m in ("capex_opex", "capex+opex", "capex-opex", "all"):
    #         add("budget-mode", "all")

    if bm_in not in (None, "",):
        m = str(bm_in).strip().lower()

        if m in {"capex", "purchase", }:
            add("budget-mode", "purchase", )
        elif m in {"capex_opex", "capex+opex", "capex-opex", "all", }:
            add("budget-mode", "all", )
        else:
            raise ValueError(f"budget_mode non valido: {bm_in}")

    # Obiettivo e lambda: prendi dal frontend, metti default che spende
    # obj = p.get("objective") or "max_cover_budget"
    # add("objective", obj)
    obj = str(p.get("objective") or "max_cover_budget").strip().lower()
    if obj not in {"min_cost", "max_cover_budget", }:
        raise ValueError(f"objective non valido: {obj}")
    add("objective", obj, )

    lc = p.get("lambda_cost")
    # print(lc)
    if lc not in (None, "",):
        add("lambda-cost", lc)

    # # turnoff-doctor-families: rispetta ciò che arriva (default 'auto')
    # if has_flag("--turnoff-doctor-families"):
    #     val = p.get("turnoff_doctor_families", "auto")
    #     add("turnoff-doctor-families", val)
    # add("turnoff-doctor-families", "auto")

    turnoff_doctor_families = str(p.get("turnoff_doctor_families", "auto", )).strip().lower()

    if turnoff_doctor_families not in {"auto", "on", "off", }:
        raise ValueError("turnoff_doctor_families " f"non valido: " f"{turnoff_doctor_families}")
    add("turnoff-doctor-families", turnoff_doctor_families, )

    # Verbose (es. '--verbose')
    vb = p.get("verbose")
    if vb:
        args.append(vb)

    return args, out_dir, Path(data_dir), severity_metadata


# ====== ROUTES ======

# Config per il frontend (ritorna il mount web, NON il path disco)
@app.route("/api/config")
def api_config():
    return jsonify({"data_dir": DATA_MOUNT})


@app.get("/api/118/severity/demand.csv")
def api_118_severity_demand():
    """
    Espone alla mappa 118 la stessa sorgente di domanda
    selezionata per l'ottimizzatore. Il browser passa soltanto source + scenario ID.
    Non può specificare path arbitrari.
    """

    severity_source = request.args.get("severity_source", "original", )
    severity_scenario_id = request.args.get("severity_scenario_id", "", )

    try:
        demand_path, metadata = (_resolve_118_demand_for_source(severity_source, severity_scenario_id, ))
        response = send_file(demand_path, mimetype="text/csv", as_attachment=False, download_name=demand_path.name, )

        # La sorgente può cambiare dalla UI: non voglio una vecchia versione dalla cache.
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Severity-Source"] = metadata["severity_source"]
        response.headers["X-Severity-Scenario-Id"] = (metadata["severity_scenario_id"] or "")
        response.headers["X-Severity-Run-Id"] = (metadata["source_run_id"] or "")
        response.headers["X-Severity-Indicator"] = (metadata["indicator"] or "")
        response.headers["X-Demand-Kind"] = metadata["demand_kind"]
        return response

    except ValueError as exc:
        return jsonify(ok=False, error=str(exc), ), 400

    except FileNotFoundError as exc:
        return jsonify(ok=False, error=str(exc), ), 404


# Servizio file dataset (disco -> web)
@app.route(f"{DATA_MOUNT}/<path:filename>")
def serve_dataset(filename):
    return send_from_directory(DATA_DIR_FS, filename)


# Servizio file run (disco -> web)
@app.route(f"{RUNS_MOUNT}/<path:filename>")
def serve_runs(filename):
    return send_from_directory(RUNS_DIR_FS, filename)


# 118 EXPLAIN RESULTS — DETERMINISTIC CONTEXT
@app.get("/api/118/explain/context/<run_id>")
def api_118_explain_context(run_id: str):
    """
    Restituisce il contesto deterministico necessario
    per spiegare un run 118.
    Nessun LLM viene invocato da questo endpoint.
    Query param opzionale: compare_with=<run_id>
    Se compare_with è presente, il confronto è ammesso
    esclusivamente tra:
        - un run Original;
        - un run Population Health.
    Il backend determina autonomamente quale dei due
    sia Original e quale Population Health.
    """

    compare_with = str(request.args.get("compare_with", "") or "").strip()
    try:

        # RUN PRINCIPALE
        run_dir = _resolve_118_run_dir(run_id)
        summary = build_118_run_summary(run_dir)
        semantics = (get_118_run_summary_semantics())
        comparison = None
        reference_run_id = None

        # CONFRONTO OPZIONALE
        if compare_with:
            comparison_dir = (_resolve_118_run_dir(compare_with))
            comparison_summary = (build_118_run_summary(comparison_dir))
            current_source = (summary["provenance"]["severity_source"])
            comparison_source = (comparison_summary["provenance"]["severity_source"])

            # Il confronto scientificamente interpretabile è esclusivamente Original vs Population Health.
            if {current_source, comparison_source} != {"original", "population_health"}:
                raise Run118SummaryError("Il confronto Explain Results 118 richiede un run Original e un run "
                                         "Population Health.")

            # compare_118_run_summaries richiede:
            # primo argomento  = Original
            # secondo argomento = Population Health.
            if current_source == "original":
                original_dir = run_dir
                ph_dir = comparison_dir
            else:
                original_dir = comparison_dir
                ph_dir = run_dir

            comparison = (compare_118_run_summaries(original_dir, ph_dir))
            reference_run_id = compare_with

        # RESPONSE
        return jsonify(
            {
                "status": "ok",
                "contract": "118_explain_context_v1",
                # Serve anche come garanzia esplicita per frontend/debug:
                # questo endpoint non ha chiamato un LLM.
                "llm_used": False,
                "run_id": run_id,
                "reference_run_id": reference_run_id,
                "mode": ("comparison" if comparison is not None else "single_run"),
                "summary": summary,
                "comparison": comparison,
                "semantics": semantics,
            }
        ), 200

    # INVALID INPUT
    except ValueError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "validation_error",
                "message": str(exc),
            }
        ), 400

    # RUN NOT FOUND
    except FileNotFoundError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "run_not_found",
                "message": str(exc),
            }
        ), 404


    # SUMMARY / COMPARISON NOT AVAILABLE
    except Run118SummaryError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "explain_context_unavailable",
                "message": str(exc),
            }
        ), 422

    # INTERNAL ERROR
    except Exception:
        app.logger.exception("Errore durante la costruzione "
                             "del contesto Explain Results 118 "
                             "per run %s", run_id)

        return jsonify(
            {
                "status": "error",
                "error": "internal_error",
                "message": "Impossibile costruire il contesto di spiegazione del run 118.",
            }
        ), 500

# ============================================================
# 118 EXPLAIN RESULTS — FINAL EXPLANATION
# ============================================================

@app.get("/api/118/explain/<run_id>")
def api_118_explain(
    run_id: str,
):
    """
    Genera una spiegazione semplice dei risultati 118.

    Pipeline:
        artifact
        -> deterministic summary
        -> controlled grounding payload
        -> LLM attempt
        -> grounding validation
        -> deterministic fallback se necessario

    Query param opzionale:
        compare_with=<run_id>

    Il confronto è ammesso esclusivamente tra
    un run Original e un run Population Health.
    """

    compare_with = str(
        request.args.get(
            "compare_with",
            "",
        )
        or ""
    ).strip()


    try:

        # CURRENT RUN
        run_dir = _resolve_118_run_dir(run_id)
        summary = build_118_run_summary(run_dir)
        resource_allocation = (build_118_resource_allocation(summary))
        semantics = (get_118_run_summary_semantics())


        # ====================================================
        # OPTIONAL COMPARISON
        # ====================================================

        comparison = None
        reference_run_id = None


        if compare_with:

            comparison_dir = (
                _resolve_118_run_dir(
                    compare_with
                )
            )

            comparison_summary = (
                build_118_run_summary(
                    comparison_dir
                )
            )


            current_source = (
                summary[
                    "provenance"
                ][
                    "severity_source"
                ]
            )

            reference_source = (
                comparison_summary[
                    "provenance"
                ][
                    "severity_source"
                ]
            )


            # Il confronto Explain Results ha significato
            # solo Original vs Population Health.
            if {
                current_source,
                reference_source,
            } != {
                "original",
                "population_health",
            }:

                raise Run118SummaryError(
                    "Il confronto Explain Results 118 "
                    "richiede un run Original e un run "
                    "Population Health."
                )


            # compare_118_run_summaries mantiene sempre
            # la direzione:
            #
            # Population Health - Original
            if current_source == "original":

                original_dir = (
                    run_dir
                )

                ph_dir = (
                    comparison_dir
                )

            else:

                original_dir = (
                    comparison_dir
                )

                ph_dir = (
                    run_dir
                )


            comparison = (
                compare_118_run_summaries(
                    original_dir,
                    ph_dir,
                )
            )

            reference_run_id = (
                compare_with
            )


        # ====================================================
        # CONTROLLED LLM PAYLOAD
        # ====================================================

        payload = build_118_llm_payload(

            summary=summary,

            semantics=semantics,

            comparison=comparison,
        )


        # ====================================================
        # EXPLANATION
        #
        # explain_118_payload() garantisce:
        #
        # LLM accepted
        #     oppure
        # deterministic fallback.
        # ====================================================

        explanation_result = (
            explain_118_payload(
                payload
            )
        )


        # ====================================================
        # RESPONSE
        # ====================================================

        return jsonify(
            {
                "status": "ok",
                "contract": "118_explain_api_v1",
                "run_id": run_id,
                "reference_run_id": reference_run_id,
                "mode":explanation_result["mode"],
                "provider": explanation_result["provider"],
                "model": explanation_result["model"],
                "generation":explanation_result["generation"],
                "validation":explanation_result["validation"],
                "explanation":explanation_result["explanation"],
                "resource_allocation": resource_allocation,
                # Provenance minima utile al frontend.
                "provenance": {
                    "severity_source": summary["provenance"]["severity_source"],
                    "indicator": summary["provenance"].get("indicator"),
                    "population_health_source_run_id": summary["provenance"].get("source_run_id"),
                },
            }
        ), 200


    # ========================================================
    # INVALID RUN ID
    # ========================================================

    except ValueError as exc:

        return jsonify(
            {
                "status":
                    "error",

                "error":
                    "validation_error",

                "message":
                    str(exc),
            }
        ), 400


    # ========================================================
    # RUN NOT FOUND
    # ========================================================

    except FileNotFoundError as exc:

        return jsonify(
            {
                "status":
                    "error",

                "error":
                    "run_not_found",

                "message":
                    str(exc),
            }
        ), 404


    # ========================================================
    # SUMMARY / COMPARISON ERROR
    # ========================================================

    except Run118SummaryError as exc:

        return jsonify(
            {
                "status":
                    "error",

                "error":
                    "explain_context_unavailable",

                "message":
                    str(exc),
            }
        ), 422


    # ========================================================
    # PAYLOAD ERROR
    # ========================================================

    except Run118ExplainPayloadError as exc:

        return jsonify(
            {
                "status":
                    "error",

                "error":
                    "explain_payload_error",

                "message":
                    str(exc),
            }
        ), 422


    # ========================================================
    # LLM PIPELINE ERROR
    #
    # Nota:
    # Ollama offline normalmente NON arriva qui perché
    # explain_118_payload usa il fallback deterministico.
    # ========================================================

    except (
        Run118ExplainLLMUnavailableError,
        Run118ExplainLLMError,
    ) as exc:

        return jsonify(
            {
                "status":
                    "error",

                "error":
                    "explanation_generation_error",

                "message":
                    str(exc),
            }
        ), 422


    # ========================================================
    # INTERNAL ERROR
    # ========================================================

    except Exception:

        app.logger.exception(
            "Errore Explain Results 118 "
            "per run %s",
            run_id,
        )

        return jsonify(
            {
                "status":
                    "error",

                "error":
                    "internal_error",

                "message": (
                    "Impossibile generare "
                    "la spiegazione del run 118."
                ),
            }
        ), 500

# Avvio di un run
@app.post("/api/run")
def api_run():
    payload = request.get_json(force=True, silent=True) or {}
    # args, out_dir, data_dir = build_cmd(payload)
    try:
        args, out_dir, data_dir, severity_metadata = build_cmd(payload)
    except (ValueError, FileNotFoundError) as exc:
        return jsonify(ok=False, error=str(exc), ), 400

    # preflight prima del run
    ok, missing, demand_used = preflight(data_dir)
    if not ok:
        return jsonify(
            ok=False,
            missing=missing,
            error="Dati mancanti",
            out_dir=str(out_dir),
            cmd=" ".join(shlex.quote(a) for a in args),
        )

    try:
        proc = subprocess.run(args, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=_allocator_subprocess_env())
        # path relativo per link web
        rel = out_dir.relative_to(BASE_DIR)
        out_web = "/" + rel.as_posix()
        return jsonify(
            ok=(proc.returncode == 0),
            out_dir=str(out_dir),
            out_web=out_web,
            stdout=proc.stdout,
            stderr=proc.stderr,
            cmd=" ".join(shlex.quote(a) for a in args),
            severity=severity_metadata
        )
    except Exception as e:
        return jsonify(
            ok=False,
            error=str(e),
            out_dir=str(out_dir),
            cmd=" ".join(shlex.quote(a) for a in args),
        )


@app.post("/api/evaluate")
def api_evaluate():
    """
    Valuta un piano proposto dall'utente (senza ottimizzare).
    Il payload accetta gli stessi parametri di /api/run + 'plan'.
    """
    payload = request.get_json(force=True, silent=True) or {}

    # OUT dir stile run (così la dashboard riusa gli stessi CSV)
    out_dir = BASE_DIR / "runs" / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    # ---- parametri base (uguali a /api/run) ----
    thresholds_map = alloc.parse_map(payload.get("T"), float) or alloc.parse_map("ROSSO=8,GIALLO=20,VERDE=30,BIANCO=45",
                                                                                 float)
    type_speed = alloc.parse_map(payload.get("type_speed"), float) or alloc.parse_map(
        "AUTO_MED=0.90,AMB_ALS=0.98,AMB_ILS=1.00", float)
    purchase_costs = alloc.parse_map(payload.get("purchase_costs"), float) or alloc.parse_map(
        "AUTO_MED=500000,AMB_ALS=350000,AMB_ILS=250000", float)
    opex_costs = alloc.parse_map(payload.get("opex_costs"), float) or alloc.parse_map(
        "AUTO_MED=250000,AMB_ALS=200000,AMB_ILS=150000", float)

    staff_per_type = alloc.parse_map(payload.get("staff_per_type"), float)
    if not staff_per_type:
        staff_per_type = {"AUTO_MED": 3.0, "AMB_ALS": 3.0, "PSAUT": 6.0}

    doctor_codes_req = alloc.parse_doctor_codes(payload.get("doctor_codes", ""))
    doctor_cover_mode = payload.get("doctor_cover", "off")
    bases = payload.get("bases", "ATT_POT")
    limit_bases = int(payload.get("limit_bases") or 0)
    full_cov = payload.get("full_coverage", "strict")
    psaut_min = int(payload.get("psaut_min") or 0)
    psaut_exact_in = payload.get("psaut_exact")
    psaut_exact = int(psaut_exact_in) if psaut_exact_in not in (None, "",) else None
    reloc_psaut = (str(payload.get("reloc_psaut", "off")).lower() == "on")

    # ---- NOVITÀ: parametri infermieri dal payload ----
    nurses_per_type = alloc.parse_map(payload.get("nurses_per_type"), float) or {}
    nurses_total_in = payload.get("nurses_total")
    nurses_total = float(nurses_total_in) if (nurses_total_in not in (None, "", "null")) else None
    nurse_unit_opex_in = payload.get("nurse_unit_opex")
    nurse_unit_opex = float(nurse_unit_opex_in) if (nurse_unit_opex_in not in (None, "", "null")) else None

    # Piano proposto
    plan = payload.get("plan") or []  # lista di {base_comune, tipo, qty, source}

    # Determina il dataset effettivo:
    # - original -> dataset/data
    # - population_health -> copia run-specific con weighted demand PH
    try:
        data_dir, severity_metadata = prepare_effective_data_dir(
            payload,
            out_dir,
        )
    except (ValueError, FileNotFoundError) as exc:
        return jsonify(
            ok=False,
            error=str(exc),
        ), 400

    # Preflight sul dataset realmente utilizzato
    ok, missing, _ = preflight(data_dir)
    if not ok:
        return jsonify(ok=False, error="Dati mancanti", missing=missing)

    try:
        metrics = alloc.evaluate_plan(
            data_dir=data_dir,
            out_dir=out_dir,
            thresholds_map=thresholds_map,
            type_speed=type_speed,
            purchase_costs=purchase_costs,
            opex_costs=opex_costs,
            bases=bases,
            limit_bases=limit_bases,
            full_coverage=full_cov,
            doctors_per_type=staff_per_type,
            doctor_codes_req=doctor_codes_req,
            doctor_cover_mode=doctor_cover_mode,
            psaut_min=psaut_min,
            psaut_exact=psaut_exact,
            reloc_psaut=reloc_psaut,
            plan=plan,
            # >>> passaggio parametri infermieri <<<
            nurses_per_type=nurses_per_type,
            nurse_unit_opex=nurse_unit_opex,
            nurses_total=nurses_total,
        )
        rel = out_dir.relative_to(BASE_DIR)
        out_web = "/" + rel.as_posix()
        return jsonify(
            ok=True,
            out_dir=str(out_dir),
            out_web=out_web,
            metrics=metrics,
            doctors_used=metrics.get("doctors_used"),
            nurses_used=metrics.get("nurses_used"),
            nurses_total=nurses_total,
            severity=severity_metadata
        )

    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ============================================================
# PROMETHEUS INTERACTIVE STRATIFICATION
# ============================================================

@app.post("/api/stratification/run")
def api_stratification_run():
    """
    Avvia una stratificazione PROMETHEUS interattiva.
    """
    payload = request.get_json(silent=True)

    if payload is None:
        return jsonify(
            {
                "status": "error",
                "error": {"type": "validation_error",
                          "message": ("Il body della richiesta deve essere un oggetto JSON."), "field": None, },
            }
        ), 400

    try:
        result = run_stratification_request(payload)
        return jsonify(result), 200

    except StratificationRequestValidationError as exc:
        return jsonify(
            {
                "status": "error",
                "error": {"type": "validation_error", "message": str(exc), "field": exc.field, },
            }
        ), 400

    except InteractiveRunNotFeasibleError as exc:
        return jsonify(
            {
                "status": "not_feasible",
                "error": {"type": "scientific_feasibility_error", "stage": exc.stage, "prometheus_status": exc.status,
                          "message": str(exc), "details": exc.details, },
            }
        ), 422

    except Exception:
        app.logger.exception("Errore inatteso durante PROMETHEUS interactive stratification")

        return jsonify(
            {
                "status": "error",
                "error": {"type": "internal_error",
                          "message": "Errore interno durante l'esecuzione della stratificazione.", },
            }
        ), 500


@app.get("/api/stratification/results/<run_id>")
def api_stratification_results(run_id: str, ):
    """
    Restituisce gli artifact di un run PROMETHEUS già completato.
    Query params:
    - page: pagina CSV, default 1;
    - page_size: righe per pagina, default 25,
      massimo 100.
    """

    try:
        result = get_stratification_results(
            run_id=run_id,
            page=request.args.get("page", 1, ),
            page_size=request.args.get("page_size", 25, ),
            search=request.args.get("search"),
            baseline_level=request.args.get("baseline_level"),
            recommendation_status=(request.args.get("recommendation_status")),
            allocation_status=(request.args.get("allocation_status")),
            sort_by=request.args.get("sort_by", "patient_id", ),
            sort_direction=request.args.get("sort_direction", "asc", ),
            municipality=request.args.get("municipality"),
        )

        return jsonify(result), 200

    except StratificationRequestValidationError as exc:
        return jsonify(
            {
                "status": "error",
                "error": {"type": "validation_error", "message": str(exc), "field": exc.field, },
            }
        ), 400

    except StratificationRunNotFoundError as exc:
        return jsonify(
            {
                "status": "error",

                "error": {
                    "type": "run_not_found",
                    "message": str(exc),
                    "run_id": exc.run_id,
                },
            }
        ), 404

    except Exception:

        app.logger.exception(
            "Errore durante la lettura "
            "dei risultati PROMETHEUS"
        )

        return jsonify(
            {
                "status": "error",

                "error": {
                    "type": "internal_error",

                    "message": (
                        "Errore interno durante "
                        "la lettura dei risultati "
                        "di stratificazione."
                    ),
                },
            }
        ), 500


@app.get("/api/stratification/geography/<run_id>")
def stratification_geography(run_id: str, ):
    try:

        result = (
            get_stratification_geography(
                run_id=run_id,
            )
        )

        return jsonify(
            result
        ), 200


    except StratificationRequestValidationError as exc:

        return jsonify(
            {
                "status": "error",
                "error": "invalid_request",
                "message": str(exc),
            }
        ), 400


    except StratificationRunNotFoundError as exc:

        return jsonify(
            {
                "status": "error",
                "error": "run_not_found",
                "message": str(exc),
            }
        ), 404


    except StratificationGeographyUnavailableError as exc:

        return jsonify(
            {
                "status": "error",
                "error": "geography_unavailable",
                "message": str(exc),
            }
        ), 422


    except Exception:

        app.logger.exception(
            "Errore durante la generazione "
            "dell'aggregazione geografica "
            "per run %s",
            run_id,
        )

        return jsonify(
            {
                "status": "error",
                "error": "internal_error",
                "message": (
                    "Impossibile generare "
                    "l'aggregazione geografica."
                ),
            }
        ), 500


@app.get(
    "/api/stratification/geography/<run_id>/geojson"
)
def stratification_geography_geojson(
        run_id: str,
):
    try:

        result = (
            get_stratification_geography_geojson(
                run_id=run_id,
            )
        )

        return jsonify(
            result
        ), 200


    except StratificationRunNotFoundError as exc:

        return jsonify(
            {
                "status": "error",
                "error":
                    "run_not_found",
                "message":
                    str(exc),
            }
        ), 404


    except StratificationGeographyUnavailableError as exc:

        return jsonify(
            {
                "status": "error",
                "error":
                    "geography_unavailable",
                "message":
                    str(exc),
            }
        ), 422


    except StratificationBoundaryDataUnavailableError as exc:

        return jsonify(
            {
                "status": "error",
                "error":
                    "boundary_data_unavailable",
                "message":
                    str(exc),
            }
        ), 503


    except Exception:

        app.logger.exception(
            "Errore durante la costruzione "
            "del GeoJSON per il run %s",
            run_id,
        )

        return jsonify(
            {
                "status": "error",
                "error":
                    "internal_error",

                "message":
                    "Impossibile costruire "
                    "la mappa territoriale.",
            }
        ), 500


# ============================================================
# POPULATION HEALTH -> 118 TERRITORIAL SEVERITY
# ============================================================

@app.post("/api/ph-118/severity/preview")
def api_ph_118_severity_preview():
    """
    Costruisce una preview della severità territoriale PH -> 118.
    Non materializza scenari e non modifica il dataset originale 118.
    """

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "status": "error",
                "error": "invalid_request",
                "message": "Il body deve essere un oggetto JSON.",
            }
        ), 400

    run_id = str(payload.get("run_id", "")).strip()
    metric = str(payload.get("metric", "")).strip()

    if not run_id:
        return jsonify(
            {
                "status": "error",
                "error": "validation_error",
                "field": "run_id",
                "message": "run_id obbligatorio.",
            }
        ), 400

    if metric not in PH_118_ALLOWED_METRICS:
        return jsonify(
            {
                "status": "error",
                "error": "validation_error",
                "field": "metric",
                "message": "Indicatore non supportato. Sono ammessi esclusivamente: patient_count e mean_baseline_need."
            }
        ), 400

    try:
        preview = preview_ph_118_severity(run_id=run_id, metric=metric, )

        # Esponiamo esclusivamente la parte JSON-safe.
        # I DataFrame interni della preview restano server-side.
        response = {
            "status": "ok",
            "run_id": preview["run_id"],
            "metric": preview["metric"],
            "severity_source": preview["severity_source"],
            "municipality_count": int(preview["municipality_count"]),
            "tier_counts": {
                key: int(value)
                for key, value
                in preview["tier_counts"].items()
            },
            "tier_shares": {
                key: float(value)
                for key, value
                in preview["tier_shares"].items()
            },
            "tier_weights": {
                key: float(value)
                for key, value
                in preview["tier_weights"].items()
            },
            "municipalities": preview["municipalities"],
        }

        return jsonify(response), 200

    except StratificationRunNotFoundError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "run_not_found",
                "message": str(exc),
            }
        ), 404

    except StratificationGeographyUnavailableError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "geography_unavailable",
                "message": str(exc),
            }
        ), 422

    except PH118SeverityError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "severity_preview_error",
                "message": str(exc),
            }
        ), 422

    except Exception:
        app.logger.exception(
            "Errore durante la preview PH -> 118 "
            "per run %s",
            run_id,
        )

        return jsonify(
            {
                "status": "error",
                "error": "internal_error",
                "message": (
                    "Errore interno durante la costruzione "
                    "della preview PH -> 118."
                ),
            }
        ), 500


@app.post("/api/ph-118/severity/materialize")
def api_ph_118_severity_materialize():
    """
    Conferma esplicita PH -> 118.
    Ricostruisce server-side la preview e materializza uno scenario separato sotto outputs/118_scenarios.
    """

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return jsonify(
            {
                "status": "error",
                "error": "invalid_request",
                "message": "Il body deve essere un oggetto JSON.",
            }
        ), 400

    run_id = str(payload.get("run_id", "")).strip()
    metric = str(payload.get("metric", "")).strip()
    if not run_id:
        return jsonify(
            {
                "status": "error",
                "error": "validation_error",
                "field": "run_id",
                "message": "run_id obbligatorio.",
            }
        ), 400

    if metric not in PH_118_ALLOWED_METRICS:
        return jsonify(
            {
                "status": "error",
                "error": "validation_error",
                "field": "metric",
                "message": (
                    "Indicatore non supportato. Sono ammessi esclusivamente patient_count e mean_baseline_need."
                ),
            }
        ), 400

    try:
        # IMPORTANTE:
        # non utilizziamo tier/valori provenienti dal browser.
        # La preview viene ricalcolata dal backend.
        preview = preview_ph_118_severity(run_id=run_id, metric=metric, )
        materialized = materialize_ph_118_scenario(preview)
        metadata = materialized["metadata"]

        return jsonify(
            {
                "status": "ok",
                "scenario_id": materialized["scenario_id"],
                "severity": {
                    "severity_source": metadata["severity_source"],
                    "source_run_id": metadata["source_run_id"],
                    "metric": metadata["metric"],
                    "municipality_count": int(metadata["municipality_count"]),
                    "tier_counts": {
                        key: int(value)
                        for key, value in metadata["tier_counts"].items()
                    },
                    "tier_weights": {
                        key: float(value)
                        for key, value in metadata["tier_weights"].items()
                    },
                    "original_demand_modified": bool(metadata["original_demand_modified"]),
                    "emergency_codes_modified": bool(metadata["emergency_codes_modified"]),
                    "created_at": metadata["created_at"],
                },
            }
        ), 200

    except StratificationRunNotFoundError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "run_not_found",
                "message": str(exc),
            }
        ), 404

    except StratificationGeographyUnavailableError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "geography_unavailable",
                "message": str(exc),
            }
        ), 422

    except PH118SeverityError as exc:
        return jsonify(
            {
                "status": "error",
                "error": "severity_materialization_error",
                "message": str(exc),
            }
        ), 422

    except Exception:
        app.logger.exception("Errore durante la materializzazione PH -> 118 per run %s", run_id, )

        return jsonify(
            {
                "status": "error",
                "error": "internal_error",
                "message": "Errore interno durante la materializzazione dello scenario PH -> 118.",
            }
        ), 500


@app.post("/api/stratification/csv/validate")
def api_validate_stratification_csv():
    """
    Riceve un CSV patient-level, lo valida e restituisce
    il Compatibility Report. NON avvia PROMETHEUS.
    """

    uploaded_file = request.files.get("file")

    if (uploaded_file is None or not uploaded_file.filename):
        return jsonify(
            {
                "status": "error",
                "error": "Nessun file CSV ricevuto.",
            }
        ), 400

    try:
        # Leggiamo al massimo un byte oltre il limite,
        # così possiamo rilevare file troppo grandi
        # senza conservarli nel progetto.
        content = uploaded_file.stream.read(MAX_UPLOAD_BYTES + 1)

        if len(content) > MAX_UPLOAD_BYTES:
            return jsonify(
                {
                    "status": "error",
                    "error": (
                        "Il file CSV supera "
                        "la dimensione massima "
                        "consentita di 20 MB."
                    ),
                }
            ), 413

        result = (
            validate_and_stage_patient_csv(
                original_filename=(
                    uploaded_file.filename
                ),
                content=content,
            )
        )

    except PatientCsvUploadError as exc:
        return jsonify(
            {
                "status": "error",
                "error": str(exc),
            }
        ), 400

    except Exception as exc:
        print(
            "[CSV UPLOAD ERROR]",
            repr(exc),
        )

        return jsonify(
            {
                "status": "error",
                "error": (
                    "Errore interno durante "
                    "la validazione del CSV."
                ),
            }
        ), 500

    return jsonify(
        {
            "status": "validated",
            **result,
        }
    )


@app.get("/api/stratification/csv/template")
def api_download_stratification_csv_template():
    """
    Restituisce il template CSV canonico per una coorte patient-level PROMETHEUS.
    Le colonne residence_municipality e residence_postal_code sono opzionali.
    """

    try:
        # Rigenerazione deterministica:
        # garantisce che il template rimanga
        # sincronizzato con il contratto corrente.
        template_path = (write_patient_csv_template(PATIENT_CSV_TEMPLATE_PATH))

    except Exception as exc:
        print("[CSV TEMPLATE ERROR]", repr(exc), )

        return jsonify(
            {
                "status": "error",
                "error": "Impossibile generare il template CSV.",
            }
        ), 500

    return send_file(
        template_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name="prometheus_patient_dataset_template.csv",
        max_age=0
    )


# MODIFICA PER COMPATTARE HOME PAGE
# Home → index.html nella stessa cartella di server.py
# @app.get("/")
# def root():
#    return redirect("/index_modular.html", code=302)

@app.get("/")
def planning_118_page():
    return render_template(
        "planning_118.html",
        active_page="planning",
    )


@app.get("/planning-118/chatbot")
def planning_118_chatbot_page():
    return render_template(
        "planning_118_chatbot.html",
        active_page="planning",
        planning_mode="chatbot",
    )


@app.get("/population-health")
def population_health_page():
    return render_template(
        "population_health.html",
        active_page="population_health",
    )


# (opzionale) rotta esplicita per index.html, utile se vuoi forzare la sorgente
@app.get("/index.html")
def serve_index():
    return send_from_directory(BASE_DIR, "index_modular.html")


@app.post("/api/asl-assistant/validate")
def asl_assistant_validate():
    try:

        payload = request.get_json(
            silent=False
        )

        result = (
            validate_asl_assistant_request(
                payload
            )
        )

        if not result["valid"]:
            return jsonify(
                result
            ), 400

        return jsonify(
            result
        ), 200


    except ASLAssistantRequestError as exc:

        return jsonify(
            {
                "status": "error",
                "valid": False,
                "error": "invalid_request",
                "message": str(exc),
                "configuration": {},
                "preview": [],
                "errors": [],
            }
        ), 400


    except Exception:

        app.logger.exception(
            "Errore durante la validazione "
            "della configurazione ASL."
        )

        return jsonify(
            {
                "status": "error",
                "valid": False,
                "error": "internal_error",
                "message": (
                    "Impossibile validare "
                    "la configurazione ASL."
                ),
                "configuration": {},
                "preview": [],
                "errors": [],
            }
        ), 500


@app.post("/api/asl-assistant/interpret")
def asl_assistant_interpret():
    try:

        payload = request.get_json(
            silent=False
        )

        result = (
            interpret_asl_assistant_request(
                payload
            )
        )

        if result["valid"]:
            return jsonify(
                result
            ), 200

        return jsonify(
            result
        ), 422


    except ASLAssistantRequestError as exc:

        return jsonify(
            {
                "status":
                    "error",

                "valid":
                    False,

                "error":
                    "invalid_request",

                "message":
                    str(exc),

                "configuration": {},
                "preview": [],
                "errors": [],
            }
        ), 400


    except ASLAssistantLLMUnavailableError as exc:

        return jsonify(
            {
                "status":
                    "error",

                "valid":
                    False,

                "error":
                    "llm_unavailable",

                "message":
                    str(exc),

                "configuration": {},
                "preview": [],
                "errors": [],
            }
        ), 503


    except ASLAssistantInterpretationError as exc:

        app.logger.exception(
            "Errore assistente ASL."
        )

        return jsonify(
            {
                "status":
                    "error",

                "valid":
                    False,

                "error":
                    "interpretation_error",

                "message":
                    str(exc),

                "configuration": {},
                "preview": [],
                "errors": [],
            }
        ), 502


    except Exception:

        app.logger.exception(
            "Errore inatteso "
            "nell'assistente ASL."
        )

        return jsonify(
            {
                "status":
                    "error",

                "valid":
                    False,

                "error":
                    "internal_error",

                "message":
                    "Errore interno "
                    "dell'assistente ASL.",

                "configuration": {},
                "preview": [],
                "errors": [],
            }
        ), 500


if __name__ == "__main__":
    # debug=True utile in sviluppo; host/porta come usavi tu
    app.run("127.0.0.1", 8001, debug=True)
