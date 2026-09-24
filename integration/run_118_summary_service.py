from __future__ import annotations

import csv
import json

from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

# CONTRACT
SUMMARY_SCHEMA_VERSION = "run_118_summary_v1"
COMPARISON_SCHEMA_VERSION = "run_118_comparison_v1"
SEMANTICS_SCHEMA_VERSION = "run_118_summary_semantics_v1"
DEFAULT_TOP_N = 5

RESOURCE_TYPE_LABELS: dict[str, dict[str, str]] = {
    "AUTO_MED": {
        "singular": "Auto medica",
        "plural": "Auto mediche",
    },

    "PSAUT": {
        "singular":"Postazione fissa di Primo Soccorso Territoriale",
        "plural": "Postazioni fisse di Primo Soccorso Territoriale",
    },

    "CMR": {
        "singular": "Centro Mobile di Rianimazione",
        "plural": "Centri Mobili di Rianimazione",
    },

    "AMB_ILS": {
        "singular": "Ambulanza di soccorso intermedio (ILS)",
        "plural": "Ambulanze di soccorso intermedio (ILS)",
    },

    "AMB_ALS": {
        "singular": "Ambulanza di soccorso avanzato (ALS)",
        "plural": "Ambulanze di soccorso avanzato (ALS)",
    },
}


class Run118SummaryError(RuntimeError):
    """
    Errore nella costruzione del riepilogo
    deterministico di un run 118.
    """
    pass


REQUIRED_ARTIFACTS = (
    "run_input_metadata.json",
    "run_summary.csv",
    "coverage_summary.csv",
    "doctor_coverage_summary.csv",
    "chosen_slots.csv",
    "feasibility_summary.csv",
    "uncovered_by_comune_code.csv",
)

# SEMANTIC GUIDE FOR THE LLM
# IMPORTANTE:
# questo oggetto NON contiene i risultati del run  Spiega solamente che cosa significano i campi.


RUN_118_SUMMARY_SEMANTICS: dict[str, Any] = {
    "schema_version": SEMANTICS_SCHEMA_VERSION,
    "audience": "non_expert",
    "purpose": ("Glossario controllato per spiegare in linguaggio semplice i risultati dell'ottimizzazione 118."),
    "terms": {

        # PROVENANCE
        "provenance.severity_source": {
            "label": "Origine della domanda territoriale",
            "simple_meaning": (
                "Indica se l'ottimizzatore ha utilizzato la domanda 118 originale oppure"
                " una versione territorialmente pesata tramite Population Health."
            ),
        },

        "provenance.indicator": {
            "label": "Indicatore Population Health",
            "simple_meaning": (
                "Quando la sorgente è Population Health, indica quale misura territoriale è stata "
                "utilizzata per modificare il peso della domanda."
            ),
        },

        # COVERAGE
        "coverage.overall.demand": {
            "label": "Domanda totale",
            "simple_meaning": (
                "Volume complessivo di richieste 118 considerato dal modello."
            ),
        },
        "coverage.overall.covered": {
            "label": "Domanda coperta",
            "simple_meaning": (
                "Parte della domanda che la soluzione selezionata riesce a considerare coperta "
                "secondo i tempi e i vincoli configurati."
            ),
        },
        "coverage.overall.uncovered": {
            "label": "Domanda non coperta",
            "simple_meaning": (
                "Parte della domanda che rimane fuori dalla copertura prevista dalla soluzione."
            ),
        },
        "coverage.overall.coverage_pct": {
            "label": "Percentuale di copertura",
            "simple_meaning": (
                "Percentuale della domanda totale che risulta coperta. Per esempio, una "
                "copertura del 95% significa circa 95 richieste coperte ogni 100."
            ),
        },
        "coverage.by_code": {
            "label": "Copertura per codice di emergenza",
            "simple_meaning": (
                "Mostra separatamente domanda, copertura e domanda non coperta per i codici "
                "ROSSO, GIALLO, VERDE e BIANCO."
            ),
        },
        "coverage.doctor_red_yellow": {
            "label": "Copertura medica dei codici Rosso e Giallo",
            "simple_meaning": (
                "Misura la copertura con disponibilità "
                "medica considerando esclusivamente le richieste ROSSO e GIALLO."
            ),
        },

        # FLEET
        "fleet.active_units": {
            "label": "Unità attive",
            "simple_meaning": (
                "Numero complessivo di mezzi o postazioni selezionati dall'ottimizzatore."
            ),
        },
        "fleet.active_bases": {
            "label": "Basi attive",
            "simple_meaning": (
                "Numero di località nelle quali è presente almeno una unità selezionata."
            ),
        },
        "fleet.by_type": {
            "label": "Unità per tipologia",
            "simple_meaning": (
                "Indica quante unità di ogni tipologia sono presenti nella soluzione finale."
            ),
        },
        "fleet.existing_units": {
            "label": "Unità già esistenti",
            "simple_meaning": (
                "Unità selezionate che erano già presenti nella configurazione territoriale."
            ),
        },
        "fleet.new_units": {
            "label": "Nuove unità",
            "simple_meaning": (
                "Unità aggiuntive selezionate dall'ottimizzatore."
            ),
        },

        # RESOURCES
        "resources.doctors_used": {
            "label": "Risorse mediche utilizzate",
            "simple_meaning": (
                "Quantità di risorse mediche richiesta dalla soluzione secondo le regole "
                "di personale configurate nel modello."
            ),
        },

        "resources.nurses_used": {
            "label": "Risorse infermieristiche utilizzate",
            "simple_meaning": (
                "Quantità di risorse infermieristiche "
                "richiesta dalla soluzione secondo le regole configurate nel modello."
            ),
        },

        # COSTS
        "costs.purchase_cost": {
            "label": "Costo di acquisto",
            "simple_meaning": (
                "Costo associato alle nuove unità selezionate dalla soluzione."
            ),
        },
        "costs.opex_cost": {
            "label": "Costo operativo",
            "simple_meaning": (
                "Costo operativo associato alle unità selezionate."
            ),
        },
        "costs.total_cost": {
            "label": "Costo totale",
            "simple_meaning": (
                "Somma del costo di acquisto e del costo operativo riportati nel run."
            ),
        },

        # FEASIBILITY
        "feasibility.doctors_overrun": {
            "label": "Superamento disponibilità medici",
            "simple_meaning": (
                "Indica se la soluzione richiede più risorse mediche di quelle disponibili. "
                "Zero significa che il limite non è stato superato."
            ),
        },

        "feasibility.nurses_overrun": {
            "label": "Superamento disponibilità infermieri",
            "simple_meaning": (
                "Indica se la soluzione richiede più risorse infermieristiche "
                "di quelle disponibili. Zero significa che il limite non è stato superato."
            ),
        },

        "feasibility.budget_overrun": {
            "label": "Superamento budget",
            "simple_meaning": (
                "Indica di quanto la soluzione supera il budget configurato. "
                "Zero significa che il budget non è stato superato."
            ),
        },

        "feasibility.coverage_violations": {
            "label": "Vincoli di copertura non soddisfatti",
            "simple_meaning": (
                "Numero di controlli territoriali di copertura che non risultano "
                "soddisfatti. Non rappresenta il numero "
                "di chiamate non coperte."
            ),
        },

        # TERRITORY
        "territorial_criticalities.top_uncovered": {
            "label": "Principali criticità territoriali",
            "simple_meaning": (
                "Comuni e codici di emergenza con il maggiore volume di domanda non coperta."
            ),
        },
    },

    # UNIT TYPES
    "unit_types": {
        "AUTO_MED": "Automedica: mezzo di soccorso con componente medica.",
        "AMB_ALS": "Ambulanza ALS: tipologia di ambulanza avanzata prevista dal modello.",
        "AMB_ILS": "Ambulanza ILS: tipologia di ambulanza prevista dall'ottimizzatore.",
        "PSAUT": "Postazione PSAUT: presidio territoriale fisso previsto dal modello.",
        "CMR": "Centro Mobile di Rianimazione.",
    },

    # EMERGENCY CODES
    "emergency_codes": {
        "ROSSO": "Codice con priorità più elevata tra quelli rappresentati.",
        "GIALLO": "Codice ad alta priorità, inferiore al ROSSO.",
        "VERDE": "Codice con urgenza inferiore rispetto a ROSSO e GIALLO.",
        "BIANCO": "Codice con priorità più bassa tra quelli rappresentati.",
    },

    # RULES FOR THE LLM
    "interpretation_rules": [

        (
            "I numeri presenti nel summary sono "
            "calcolati deterministicamente dagli artifact "
            "del run. Il modello linguistico deve "
            "spiegarli e non ricalcolarli."
        ),

        (
            "Population Health non modifica i codici "
            "ROSSO, GIALLO, VERDE e BIANCO. "
            "Modifica esclusivamente il peso territoriale "
            "della domanda quando severity_source "
            "è population_health."
        ),

        (
            "Una percentuale di copertura più alta "
            "indica che una quota maggiore della domanda "
            "risulta coperta."
        ),

        (
            "Una quantità maggiore di domanda non coperta "
            "indica una criticità operativa maggiore."
        ),

        (
            "Una differenza tra un run Originale "
            "e un run Population Health mostra come "
            "l'ottimizzatore reagisce a una diversa "
            "distribuzione territoriale della domanda. "
            "Non deve essere descritta come prova "
            "di un effetto causale."
        ),

        (
            "coverage_violations indica il numero "
            "di vincoli territoriali non soddisfatti. "
            "Non deve essere descritto come numero "
            "di chiamate o pazienti."
        ),

        (
            "Se un valore è assente o nullo, "
            "deve essere indicato come non disponibile. "
            "Non deve essere stimato o inventato."
        ),

        (
            "La spiegazione finale deve privilegiare "
            "termini semplici e comprensibili anche "
            "a un utente non tecnico."
        ),
    ],
}


# GENERIC HELPERS
def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text.replace(",", "."))

    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


def _read_csv(path: Path, ) -> list[dict[str, str]]:
    if not path.exists():
        raise Run118SummaryError(f"Artifact 118 mancante: {path.name}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise Run118SummaryError(f"Artifact 118 mancante: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError,) as exc:
        raise Run118SummaryError(f"Artifact JSON non leggibile: {path.name}") from exc

    if not isinstance(data, dict):
        raise Run118SummaryError(f"Artifact JSON non valido: {path.name}")

    return data


def _first_value(row: Mapping[str, Any], candidates: Iterable[str]) -> Any:
    keys = {str(key).strip().lower(): key for key in row.keys()}
    for candidate in candidates:
        original = keys.get(candidate.lower())

        if original is not None:
            value = row.get(original)
            if value not in (None, ""):
                return value

    return None


def _code(row: Mapping[str, Any]) -> str:
    value = _first_value(row, ("codice", "code"))
    return str(value or "").strip().upper()


# COVERAGE
def _coverage_from_rows(rows: list[dict[str, str]], *, allowed_codes: set[str] | None = None, doctor: bool = False) -> dict[str, float | None]:
    selected = rows
    if allowed_codes is not None:
        selected = [row for row in rows if _code(row) in allowed_codes]

    else:
        non_total = [row for row in rows if _code(row) != "TOTAL"]

        if non_total:
            selected = non_total

    demand = 0.0
    covered = 0.0
    uncovered = 0.0
    found_demand = False
    found_covered = False
    found_uncovered = False

    for row in selected:
        calls = _to_float(_first_value(row, ("chiamate", "total_calls", "calls"), ))
        covered_value = _to_float(_first_value(row, ("doctor_covered", "covered") if doctor else "covered"))
        uncovered_value = _to_float(_first_value(row, ("uncovered_doctor", "uncovered", "total_uncovered") if doctor else ("uncovered", "total_uncovered")))
        if calls is not None:
            demand += calls
            found_demand = True

        if covered_value is not None:
            covered += covered_value
            found_covered = True

        if uncovered_value is not None:
            uncovered += uncovered_value
            found_uncovered = True

    demand_value = demand if found_demand else None
    covered_value = covered if found_covered else None
    uncovered_value = uncovered if found_uncovered else None
    coverage_pct = None

    if demand_value is not None and uncovered_value is not None and demand_value > 0:
        coverage_pct = (100.0 * (1.0 - uncovered_value / demand_value))

    return {
        "demand": demand_value,
        "covered": covered_value,
        "uncovered": uncovered_value,
        "coverage_pct": coverage_pct,
    }


def _coverage_by_code(rows: list[dict[str, str]]) -> dict[str, dict[str, float | None]]:
    result = {}
    for code in ("ROSSO", "GIALLO", "VERDE", "BIANCO"):
        matching = [row for row in rows if _code(row) == code]
        result[code] = (_coverage_from_rows(matching, allowed_codes={code},))

    return result


# FLEET
def _fleet_summary(rows: list[dict[str, str]],) -> dict[str, Any]:
    by_type: Counter[str] = (Counter())
    by_base: Counter[str] = (Counter())
    by_base_and_type: dict[str, Counter[str]] = defaultdict(Counter)

    existing_units = 0
    new_units = 0
    doctors_need = 0.0
    nurses_need = 0.0

    for row in rows:
        unit_type = str(_first_value(row, ("tipo", "type")) or "").strip().upper()
        base = str(_first_value(row, ("base_comune", "base", "comune")) or "").strip()
        if unit_type:
            by_type[unit_type] += 1

        if base:
            by_base[base] += 1

        if base and unit_type:
            by_base_and_type[base][unit_type] += 1

        is_existing = _to_int(row.get("is_existing"))
        if is_existing == 1:
            existing_units += 1
        elif is_existing == 0:
            new_units += 1

        doctors_need += _to_float(row.get("doctors_need")) or 0.0
        nurses_need += _to_float(row.get("nurses_need")) or 0.0

    return {
        "active_units": len(rows),
        "active_bases": len(by_base),
        "by_type": dict(sorted(by_type.items())),
        "by_base": dict(sorted(by_base.items())),
        "by_base_and_type": {
            base: dict(sorted(counter.items()))
            for base, counter
            in sorted(by_base_and_type.items())
        },
        "existing_units": existing_units,
        "new_units": new_units,
        "doctors_need_from_units": doctors_need,
        "nurses_need_from_units": nurses_need,
    }


# TERRITORIAL CRITICALITIES
def _top_uncovered(rows: list[dict[str, str]], top_n: int,) -> list[dict[str, Any]]:
    items = []
    for row in rows:
        uncovered = _to_float(row.get("uncovered"))
        if uncovered is None or uncovered <= 0:
            continue

        items.append(
            {
                "municipality": str(row.get("comune") or "").strip(),
                "code": _code(row),
                "demand": _to_float(row.get("chiamate")),
                "uncovered":uncovered,
            }
        )

    items.sort(key=lambda item: (-(item["uncovered"] or 0.0), item["municipality"], item["code"]))
    return items[:top_n]


# RUN VALIDATION
def _validate_run_dir(run_dir: Path) -> None:
    if not run_dir.is_dir():
        raise Run118SummaryError(f"Directory del run 118 non trovata: {run_dir}")

    missing = [
        name
        for name
        in REQUIRED_ARTIFACTS
        if not (run_dir / name).is_file()
    ]

    if missing:
        raise Run118SummaryError("Artifact 118 mancanti: " + ", ".join(sorted(missing)))


# PUBLIC SUMMARY BUILDER
def build_118_run_summary(run_dir: str | Path, *, top_n: int = DEFAULT_TOP_N) -> dict[str, Any]:
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1 or top_n > 20:
        raise Run118SummaryError("top_n deve essere un intero tra 1 e 20.")

    directory = Path(run_dir).resolve()
    _validate_run_dir(directory)
    metadata = _read_json(directory / "run_input_metadata.json")
    run_summary_rows = _read_csv(directory / "run_summary.csv")
    coverage_rows = _read_csv(directory / "coverage_summary.csv")
    doctor_rows = _read_csv(directory / "doctor_coverage_summary.csv")
    chosen_rows = _read_csv(directory / "chosen_slots.csv")
    feasibility_rows = _read_csv(directory / "feasibility_summary.csv")
    uncovered_rows = _read_csv(directory / "uncovered_by_comune_code.csv")

    if not run_summary_rows:
        raise Run118SummaryError("run_summary.csv è vuoto.")

    if not feasibility_rows:
        raise Run118SummaryError("feasibility_summary.csv è vuoto.")

    run_row = (run_summary_rows[0])
    feasibility_row = (feasibility_rows[0])
    severity_source = str(metadata.get("severity_source") or "").strip().lower()
    severity_source = {"original": "original", "population_health": "population_health"}.get(severity_source, severity_source or "unknown")

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": directory.name,
        # PROVENANCE
        "provenance": {
            "severity_source": severity_source,
            "severity_scenario_id": metadata.get("severity_scenario_id"),
            "source_run_id": metadata.get("source_run_id"),
            "indicator": metadata.get("indicator"),
            "method":metadata.get("method"),
        },
        # COVERAGE
        "coverage": {
            "overall": _coverage_from_rows(coverage_rows),
            # IMPORTANTE: copertura medica = esclusivamente ROSSO + GIALLO. Non utilizziamo DOC_total_*.
            "doctor_red_yellow": _coverage_from_rows(doctor_rows, allowed_codes={"ROSSO", "GIALLO"}, doctor=True),
            "by_code": _coverage_by_code(coverage_rows),
        },

        # FLEET
        "fleet": _fleet_summary(chosen_rows),
        # STAFF
        "resources": {
            "doctors_used": _to_float(run_row.get("doctors_used")),
            "nurses_used": _to_float(run_row.get("nurses_used")),
        },

        # COSTS
        "costs": {
            "purchase_cost": _to_float(run_row.get("purchase_cost")),
            "opex_cost": _to_float(run_row.get("opex_cost")),
            "total_cost": _to_float(run_row.get("total_cost")),
        },

        # RUNTIME
        "runtime": {
            "elapsed_sec": _to_float(run_row.get("elapsed_sec")),
        },

        # FEASIBILITY: non riportiamo doc_pct: la metrica medica canonica rimane
        # coverage.doctor_red_yellow.
        "feasibility": {
            "doctors_overrun": _to_float(feasibility_row.get("doctors_overrun_staff")),
            "nurses_overrun": _to_float(feasibility_row.get("nurses_overrun_staff")),
            "budget_overrun": _to_float(feasibility_row.get("budget_overrun_cost")),
            "coverage_checks": _to_int(feasibility_row.get("cov_total")),
            "coverage_violations": _to_int(feasibility_row.get("cov_viol")),
        },

        # TERRITORIAL CRITICALITIES
        "territorial_criticalities": {"top_uncovered": _top_uncovered(uncovered_rows, top_n)},
    }


# PUBLIC SEMANTIC CONTRACT
def get_118_run_summary_semantics() -> dict[str, Any]:
    # il chiamante non può modificare accidentalmente il contratto globale.
    return deepcopy(RUN_118_SUMMARY_SEMANTICS)


# COMPARISON HELPERS
def _comparison_value(original: float | int | None, population_health: float | int | None, *, delta_unit: str = "absolute") -> dict[str, Any]:
    if original is None or population_health is None:
        difference = None
    else:
        difference = population_health - original

    return {
        "original": original,
        "population_health": population_health,
        "delta": difference,
        "delta_direction": "population_health_minus_original",
        "delta_unit":delta_unit,
    }


def _compare_metric_group(original: Mapping[str, Any], population_health: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for metric in ("demand", "covered", "uncovered", "coverage_pct",):
        delta_unit = ("percentage_points" if metric == "coverage_pct" else "absolute")

        result[metric] = _comparison_value(original.get(metric), population_health.get(metric), delta_unit=delta_unit)
    return result


def _compare_counts(original: Mapping[str, Any], population_health: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    keys = sorted(set(original) | set(population_health))

    for key in keys:
        original_value = int(original.get(key, 0) or 0)
        ph_value = int(population_health.get(key, 0) or 0 )
        result[key] = {
            "original": original_value,
            "population_health": ph_value,
            "delta": ph_value - original_value,
        }

    return result


def _changed_bases(original: Mapping[str, Mapping[str, Any]], population_health: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:

    changed = []
    bases = sorted(set(original) | set(population_health))
    for base in bases:
        original_types = {
            str(key): int(value or 0)
            for key, value
            in (original.get(base, {})).items()
        }

        ph_types = {
            str(key): int(value or 0)
            for key, value
            in (population_health.get(base, {})).items()
        }

        if original_types == ph_types:
            continue

        changed.append(
            {
                "base": base,
                "original": dict(sorted(original_types.items())),
                "population_health": dict(sorted(ph_types.items())),
            }
        )
    return changed


# PUBLIC ORIGINAL vs POPULATION HEALTH COMPARISON
def compare_118_run_summaries(original_run_dir: str | Path, population_health_run_dir: str | Path, *, top_n: int = DEFAULT_TOP_N) -> dict[str, Any]:
    original = build_118_run_summary(original_run_dir, top_n=top_n)
    population_health = build_118_run_summary(population_health_run_dir, top_n=top_n)
    original_source = (original["provenance"]["severity_source"])
    ph_source = (population_health["provenance"]["severity_source"])

    if original_source != "original":
        raise Run118SummaryError("Il primo run del confronto deve avere severity_source='original'.")

    if ph_source != "population_health":
        raise Run118SummaryError("Il secondo run del confronto deve avere severity_source='population_health'.")

    original_fleet = (original["fleet"])
    ph_fleet = (population_health["fleet"])
    changed_bases = _changed_bases(
        original_fleet.get("by_base_and_type", {}),
        ph_fleet.get("by_base_and_type", {}),
    )

    # COVERAGE BY CODE
    coverage_by_code = {}
    for code in ("ROSSO", "GIALLO", "VERDE", "BIANCO",):
        coverage_by_code[code] = _compare_metric_group(
            original["coverage"]["by_code"].get(code, {}),
            population_health["coverage"]["by_code"].get(code, {}),
        )
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_direction": "population_health_minus_original",
        # RUNS
        "runs": {
            "original_run_id": original["run_id"],
            "population_health_run_id": population_health["run_id"],
        },
        # PH PROVENANCE
        "population_health_provenance": {
            "severity_scenario_id": population_health["provenance"].get("severity_scenario_id"),
            "source_run_id": population_health["provenance"].get("source_run_id"),
            "indicator": population_health["provenance"].get("indicator"),
            "method": population_health["provenance"].get("method"),
        },

        # COVERAGE
        "coverage": {
            "overall": _compare_metric_group(
                    original["coverage"]["overall"],
                    population_health["coverage"]["overall"],
                ),
            "doctor_red_yellow": _compare_metric_group(
                    original["coverage"]["doctor_red_yellow"],
                    population_health["coverage"]["doctor_red_yellow"]
                ),
            "by_code": coverage_by_code,
        },

        # FLEET / ALLOCATION
        "fleet": {

            "active_units": _comparison_value(
                    original_fleet.get("active_units"),
                    ph_fleet.get("active_units")
                ),
            "active_bases": _comparison_value(
                    original_fleet.get("active_bases"),
                    ph_fleet.get("active_bases")
                ),
            "by_type": _compare_counts(
                    original_fleet.get("by_type", {}),
                    ph_fleet.get("by_type", {}),
                ),
            "changed_base_count": len(changed_bases),
            "changed_bases": changed_bases,
        },
        # RESOURCES
        "resources": {
            "doctors_used": _comparison_value(
                    original["resources"].get("doctors_used"),
                    population_health["resources"].get("doctors_used")
                ),
            "nurses_used": _comparison_value(
                    original["resources"].get("nurses_used"),
                    population_health["resources"].get("nurses_used")
                )
        },
        # COSTS
        "costs": {
            key: _comparison_value(
                original["costs"].get(key),
                population_health["costs"].get(key)
            )
            for key in ("purchase_cost", "opex_cost", "total_cost")
        },

        # FEASIBILITY
        "feasibility": {
            key: _comparison_value(
                original["feasibility"].get(key),
                population_health["feasibility"].get(key),
            )
            for key in ("doctors_overrun", "nurses_overrun", "budget_overrun", "coverage_checks", "coverage_violations")
        },

        # TERRITORIAL CRITICALITIES conserviamo semplicemente le due top-list.
        "territorial_criticalities": {
            "original_top_uncovered": original["territorial_criticalities"]["top_uncovered"],
            "population_health_top_uncovered": population_health["territorial_criticalities"]["top_uncovered"]
        }
    }


RUN_118_SUMMARY_SEMANTICS["terms"].update(
    {
        "comparison.delta": {
            "label": "Variazione",
            "simple_meaning": (
                "Differenza tra il risultato ottenuto con Population Health e quello ottenuto "
                "con i dati originali. Il calcolo è sempre Population Health meno Originale."
            ),
        },

        "comparison.coverage_pct_delta": {
            "label": "Variazione della copertura",
            "simple_meaning": (
                "Indica di quanti punti percentuali cambia la quota di domanda coperta. "
                "Per esempio, da 95% a 94% la variazione è -1 punto percentuale."
            ),
        },

        "comparison.uncovered_delta": {
            "label":"Variazione della domanda non coperta",
            "simple_meaning": (
                "Un valore positivo significa che nel run Population Health rimane "
                "più domanda non coperta. Un valore negativo significa che ne rimane meno."
            ),
        },

        "comparison.demand_delta": {
            "label": "Variazione della domanda",
            "simple_meaning": (
                "Indica quanto cambia il volume di domanda considerato dall'ottimizzatore dopo "
                "l'applicazione della pesatura territoriale Population Health."
            ),
        },

        "comparison.fleet.by_type": {
            "label": "Cambiamenti nelle tipologie di mezzi",
            "simple_meaning": (
                "Mostra se la soluzione Population Health  utilizza più o meno unità di ciascuna "
                "tipologia rispetto alla soluzione originale."
            ),
        },

        "comparison.fleet.changed_bases": {
            "label":"Basi con allocazione modificata",
            "simple_meaning": (
                "Elenco delle basi nelle quali cambia la composizione dei mezzi selezionati "
                "tra la soluzione Originale e quella Population Health."
            ),
        },

        "comparison.cost_delta": {
            "label":"Variazione dei costi",
            "simple_meaning": (
                "Indica quanto cambia il costo della soluzione Population Health rispetto "
                "alla soluzione originale."
            ),
        },
    }
)


RUN_118_SUMMARY_SEMANTICS["interpretation_rules"].extend(
    [
        "Nel confronto, delta è sempre calcolato come Population Health meno Originale.",
        (
            "Le differenze delle percentuali di copertura devono essere espresse in "
            "punti percentuali, non come variazioni percentuali relative."
        ),

        (
            "Un aumento della domanda nel run  Population Health non significa che siano "
            "realmente avvenute più chiamate. Può derivare dalla pesatura territoriale "
            "applicata alla domanda originale."
        ),
        (
            "Un aumento della domanda non coperta rappresenta un peggioramento operativo "
            "della copertura nel modello."
        ),
        (
            "Una diminuzione della domanda non coperta rappresenta un miglioramento operativo "
            "della copertura nel modello."
        ),
        (
            "Una base modificata indica che cambia la composizione dei mezzi selezionati "
            "o che una unità viene aggiunta/rimossa in quella base."
        ),
        (
            "Le differenze Originale vs Population Health "
            "descrivono una risposta dell'ottimizzatore "
            "a una diversa pesatura territoriale. "
            "Non rappresentano un effetto causale di Population Health."
        ),
    ]
)


# RESOURCE ALLOCATION FOR NON-EXPERT UI
def build_118_resource_allocation( summary: Mapping[str, Any]) -> dict[str, Any]:
    """
    Costruisce la distribuzione territoriale
    delle risorse selezionate dall'ottimizzatore.
    Fonte
        summary["fleet"]["by_base_and_type"]
    Nessun LLM viene utilizzato.
    """

    fleet = summary.get("fleet", {})
    by_base_and_type = fleet.get("by_base_and_type", {})
    bases = []
    for base, resources in sorted(by_base_and_type.items()):
        rendered_resources = []
        for type_code, raw_count in sorted(resources.items()):
            count = int(raw_count or 0)
            if count <= 0:
                continue

            labels = (RESOURCE_TYPE_LABELS.get(type_code, {"singular": str(type_code), "plural": str(type_code)},))
            label = (labels["singular"] if count == 1 else labels["plural"])
            rendered_resources.append(
                {
                    "type_code": type_code,
                    "count": count,
                    "label": label,
                    "display_text": f"{count} {label}",
                }
            )

        if not rendered_resources:
            continue
        bases.append({"base": str(base).strip(), "resources": rendered_resources})
    return {
        "contract": "118_resource_allocation_v1",
        "source": "chosen_slots.csv",
        "deterministic": True,
        "active_base_count": len(bases),
        "active_unit_count":int(fleet.get("active_units", 0) or 0),
        "bases": bases,
    }