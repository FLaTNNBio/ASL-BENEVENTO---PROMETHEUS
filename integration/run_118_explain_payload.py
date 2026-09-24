from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

LLM_PAYLOAD_CONTRACT = "118_llm_grounded_payload_v1"


class Run118ExplainPayloadError(RuntimeError):
    pass


# HELPERS
def _number(value: Any, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    rounded = round(number, digits)
    if rounded.is_integer():
        return int(rounded)

    return rounded


def _coverage_presentation(coverage: Mapping[str, Any]) -> dict[str, Any]:
    pct = coverage.get("coverage_pct")
    uncovered = coverage.get("uncovered")
    demand = coverage.get("demand")
    covered_per_100 = None

    if pct is not None:
        covered_per_100 = int(round(float(pct)))

    return {
        "demand": _number(demand, 2),
        "uncovered": _number(uncovered, 2),
        "coverage_pct": _number(pct, 2),
        # Già calcolato deterministicamente. L'LLM non deve ricavarlo da solo.
        "covered_requests_per_100_approx": covered_per_100,
    }


def _comparison_metric_presentation(metric: Mapping[str, Any], *, digits: int = 2, ) -> dict[str, Any]:
    return {
        "original": _number(metric.get("original"), digits),
        "population_health": _number(metric.get("population_health"), digits),
        "delta": _number(metric.get("delta"), digits),
        "delta_unit": metric.get("delta_unit"),
    }


def _source_label(severity_source: str, ) -> str:
    if severity_source == "original":
        return "Domanda 118 originale"
    if severity_source == "population_health":
        return "Domanda 118 pesata territorialmente con Population Health"

    return "Origine della domanda non disponibile"


# SEMANTICS SELECTION
BASE_TERM_KEYS = (
    "provenance.severity_source",
    "provenance.indicator",
    "coverage.overall.demand",
    "coverage.overall.covered",
    "coverage.overall.uncovered",
    "coverage.overall.coverage_pct",
    "coverage.by_code",
    "coverage.doctor_red_yellow",
    "fleet.active_units",
    "fleet.active_bases",
    "fleet.by_type",
    "fleet.existing_units",
    "fleet.new_units",
    "resources.doctors_used",
    "resources.nurses_used",
    "costs.purchase_cost",
    "costs.opex_cost",
    "costs.total_cost",
    "feasibility.doctors_overrun",
    "feasibility.nurses_overrun",
    "feasibility.budget_overrun",
    "feasibility.coverage_violations",
    "territorial_criticalities.top_uncovered",
)

COMPARISON_TERM_KEYS = (
    "comparison.delta",
    "comparison.coverage_pct_delta",
    "comparison.uncovered_delta",
    "comparison.demand_delta",
    "comparison.fleet.by_type",
    "comparison.fleet.changed_bases",
    "comparison.cost_delta",
)


def _selected_semantics(semantics: Mapping[str, Any], *, comparison_enabled: bool, unit_types: set[str]) -> dict[
    str, Any]:
    all_terms = semantics.get("terms", {})
    term_keys = list(BASE_TERM_KEYS)
    if comparison_enabled:
        term_keys.extend(COMPARISON_TERM_KEYS)

    selected_terms = {
        key: deepcopy(all_terms[key])
        for key in term_keys
        if key in all_terms
    }

    all_unit_types = semantics.get("unit_types", {})
    selected_unit_types = {
        key: all_unit_types[key]
        for key in sorted(
            unit_types
        )
        if key in all_unit_types
    }

    return {
        "audience": semantics.get("audience", "non_expert"),
        "terms": selected_terms,
        "unit_types": selected_unit_types,
        "emergency_codes": deepcopy(semantics.get("emergency_codes", {})),
        "interpretation_rules": deepcopy(semantics.get("interpretation_rules", [])),
    }


def _format_it_number(value: Any, digits: int = 2, ) -> str:
    number = _number(value, digits)
    if number is None:
        return "non disponibile"

    if isinstance(number, int):
        return f"{number:,}".replace(",", ".", )

    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    integer_part, _, decimal_part = (text.partition("."))
    integer_value = int(integer_part)
    integer_text = (f"{integer_value:,}".replace(",", ".", ))

    if decimal_part:
        return f"{integer_text},{decimal_part}"

    return integer_text


def _change_word(delta: float | int | None) -> str:
    if delta is None:
        return "non disponibile"

    if delta > 0:
        return "aumenta"

    if delta < 0:
        return "diminuisce"

    return "rimane invariata"


def _build_high_level_findings(
        *,
        summary: Mapping[str, Any],
        comparison: Mapping[str, Any] | None,
        current_presentation: Mapping[str, Any],
        comparison_presentation: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    severity_source = (summary.get("provenance", {}).get("severity_source"))
    is_population_health = (severity_source == "population_health")

    # 1. COPERTURA CORRENTE
    coverage = current_presentation["overall_coverage"]
    pct = coverage.get("coverage_pct")
    per_100 = coverage.get("covered_requests_per_100_approx")
    if pct is not None and per_100 is not None:
        findings.append(
            {
                "id": "overall_coverage",
                "statement": (
                    "La copertura complessiva è "
                    f"{_format_it_number(pct)}%, "
                    f"cioè circa {per_100} "
                    + ("unità di domanda pesata su 100 " if is_population_health else "richieste su 100 ")
                    + "risultano coperte."
                ),
                "support": {
                    "coverage_pct": pct,
                    "covered_requests_per_100_approx": per_100,
                    "reference": 100,
                },
            }
        )

    if comparison is None or comparison_presentation is None:
        return findings

    # 2. DELTA COPERTURA
    coverage_delta = (comparison_presentation["overall"]["coverage_pct"]["delta"])
    if coverage_delta is not None:
        direction = _change_word(coverage_delta)
        if coverage_delta == 0:
            statement = (
                "Rispetto alla pianificazione Originale, "
                "la percentuale di copertura complessiva "
                "rimane invariata."
            )

        else:
            statement = (
                "Rispetto alla pianificazione Originale, "
                "la copertura complessiva "
                f"{direction} di "
                f"{_format_it_number(abs(coverage_delta))} "
                "punti percentuali."
            )

        findings.append(
            {
                "id": "overall_coverage_change",
                "statement": statement,
                "support": {
                    "delta_percentage_points": coverage_delta,
                }
            }
        )

    # 3. DOMANDA NON COPERTA
    uncovered_delta = (comparison_presentation["overall"]["uncovered"]["delta"])

    if uncovered_delta is not None:
        direction = _change_word(uncovered_delta)
        if uncovered_delta == 0:
            statement = (
                "La domanda non coperta rimane "
                "invariata rispetto alla "
                "pianificazione Originale."
            )

        else:
            statement = (
                "La domanda non coperta "
                f"{direction} di "
                f"{_format_it_number(abs(uncovered_delta))} "
                "unità rispetto alla "
                "pianificazione Originale."
            )

        findings.append(
            {
                "id": "uncovered_change",
                "statement": statement,
                "support": {"delta": uncovered_delta, },
            }
        )

    # 4. COPERTURA MEDICA ROSSO + GIALLO
    doctor_delta = (comparison_presentation["doctor_red_yellow"]["coverage_pct"]["delta"])
    if doctor_delta is not None:
        direction = _change_word(doctor_delta)
        if doctor_delta == 0:
            statement = (
                "Per i codici ROSSO e GIALLO, "
                "la copertura con disponibilità medica "
                "rimane invariata."
            )

        else:
            statement = (
                "Per i codici ROSSO e GIALLO, "
                "la copertura con disponibilità medica "
                f"{direction} di "
                f"{_format_it_number(abs(doctor_delta))} "
                "punti percentuali."
            )

        findings.append(
            {
                "id": "doctor_red_yellow_change",
                "statement": statement,
                "support": {"delta_percentage_points": doctor_delta}
            }
        )

    # 5. FLEET
    active = (comparison["fleet"]["active_units"])
    fleet_changes = []
    for unit_type, values in sorted(comparison["fleet"]["by_type"].items()):
        delta = values.get("delta")
        if not delta:
            continue

        if delta > 0:
            fleet_changes.append(f"{abs(int(delta))} {unit_type} in più")
        else:
            fleet_changes.append(f"{abs(int(delta))} {unit_type} in meno")

    active_delta = active.get("delta")
    if active_delta == 0 and fleet_changes:
        statement = (
                "Il numero totale di unità rimane "
                f"{active.get('population_health')}, "
                "ma cambia la loro composizione: "
                + " e ".join(fleet_changes)
                + "."
        )

    elif active_delta is not None:
        statement = (
            "Il numero totale di unità passa da "
            f"{active.get('original')} a "
            f"{active.get('population_health')}."
        )

    else:
        statement = None

    if statement:
        findings.append(
            {
                "id": "fleet_change",
                "statement": statement,
                "support": {
                    "active_units_original": active.get("original"),
                    "active_units_population_health": active.get("population_health"),
                    "active_units_delta": active_delta,
                    "by_type": deepcopy(comparison["fleet"]["by_type"]),
                },
            }
        )

    # 6. BASI MODIFICATE
    changed_bases = (comparison["fleet"]["changed_base_count"])
    findings.append(
        {
            "id": "changed_bases",
            "statement": (
                "La composizione dei mezzi "
                "cambia in "
                f"{changed_bases} basi."
            ),
            "support": {
                "changed_base_count":
                    changed_bases,
            },
        }
    )

    # 7. COSTO TOTALE
    cost_delta = comparison_presentation["total_cost"]["delta"]
    if cost_delta is not None:
        direction = _change_word(cost_delta)

        if cost_delta == 0:
            statement = (
                "Il costo totale rimane invariato rispetto alla pianificazione Originale."
            )

        else:
            statement = (
                "Il costo totale "
                f"{direction} di "
                f"{_format_it_number(abs(cost_delta))} "
                "unità di costo rispetto alla "
                "pianificazione Originale."
            )

        findings.append(
            {
                "id": "total_cost_change",
                "statement": statement,
                "support": {"delta": cost_delta}
            }
        )
    return findings


def _build_territorial_findings(summary: Mapping[str, Any], *, max_items: int = 3) -> list[dict[str, Any]]:
    result = []
    items = (summary["territorial_criticalities"]["top_uncovered"])
    severity_source = (summary.get("provenance", {}).get("severity_source"))
    demand_label = ("unità di domanda pesata" if severity_source == "population_health" else "unità di domanda" )

    for index, item in enumerate(items[:max_items], start=1):
        municipality = item.get("municipality")
        code = item.get("code")
        uncovered = item.get("uncovered")
        if not municipality or not code or uncovered is None:
            continue

        result.append(
            {
                "id": f"territorial_{index}",
                "statement": (
                    f"{municipality}, codice {code}: "
                    f"{_format_it_number(uncovered)} "
                    f"{demand_label} risultano "
                    "non coperte."
                ),
                "support": {
                    "municipality": municipality,
                    "code": code,
                    "uncovered": uncovered,
                },
            }
        )

    return result


# PUBLIC BUILDER
def build_118_llm_payload(
        *,
        summary: Mapping[str, Any],
        semantics: Mapping[str, Any],
        comparison: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Costruisce il payload controllato verrà fornito al LLM.
    Non legge artifact.
    Non calcola KPI di dominio.
    Non invoca alcun LLM.
    """

    if summary.get("schema_version") != "run_118_summary_v1":
        raise Run118ExplainPayloadError("Summary 118 non compatibile.")

    if semantics.get("schema_version") != "run_118_summary_semantics_v1":
        raise Run118ExplainPayloadError("Semantics 118 non compatibile.")

    if comparison is not None:
        if comparison.get("schema_version") != "run_118_comparison_v1":
            raise Run118ExplainPayloadError("Comparison 118 non compatibile.")

    provenance = summary["provenance"]
    coverage = summary["coverage"]
    fleet = summary["fleet"]

    # FACTS — CURRENT RUN
    current_run_facts = {
        "run_id": summary["run_id"],
        "source": {
            "severity_source": provenance.get("severity_source"),
            "simple_label": _source_label(provenance.get("severity_source", "")),
            "indicator": provenance.get("indicator"),
            "method": provenance.get("method"),
            "population_health_source_run_id": provenance.get("source_run_id"),
        },
        "coverage": {
            "overall": deepcopy(coverage["overall"]),
            "doctor_red_yellow": deepcopy(coverage["doctor_red_yellow"]),
            "by_code": deepcopy(coverage["by_code"]),
        },
        "fleet": {
            "active_units": fleet.get("active_units"),
            "active_bases": fleet.get("active_bases"),
            "by_type": deepcopy(fleet.get("by_type", {})),
            "existing_units": fleet.get("existing_units"),
            "new_units": fleet.get("new_units")
        },
        "resources": deepcopy(summary["resources"]),
        "costs": deepcopy(summary["costs"]),
        "feasibility": deepcopy(summary["feasibility"]),
        "territorial_criticalities": deepcopy(summary["territorial_criticalities"])
    }

    # PRESENTATION — CURRENT RUN  derivati dal codice, non dal LLM.
    current_run_presentation = {
        "overall_coverage": _coverage_presentation(coverage["overall"]),
        "doctor_red_yellow_coverage": _coverage_presentation(coverage["doctor_red_yellow"]),
        "costs": {
            key: _number(value, 2)
            for key, value
            in summary["costs"].items()
        },
    }

    # COMPARISON
    comparison_facts = None
    comparison_presentation = None

    if comparison is not None:
        comparison_facts = {
            "direction": comparison.get("comparison_direction"),
            "runs": deepcopy(comparison["runs"]),
            "population_health_provenance": deepcopy(comparison["population_health_provenance"]),
            "coverage": deepcopy(comparison["coverage"]),
            "fleet": deepcopy(comparison["fleet"]),
            "resources": deepcopy(comparison["resources"]),
            "costs": deepcopy(comparison["costs"]),
            "feasibility": deepcopy(comparison["feasibility"]),
            "territorial_criticalities": deepcopy(comparison["territorial_criticalities"]),
        }

        overall_cmp = (comparison["coverage"]["overall"])
        doctor_cmp = (comparison["coverage"]["doctor_red_yellow"])
        comparison_presentation = {

            "overall": {

                "demand": _comparison_metric_presentation(overall_cmp["demand"]),
                "uncovered": _comparison_metric_presentation(overall_cmp["uncovered"]),
                "coverage_pct": _comparison_metric_presentation(overall_cmp["coverage_pct"], digits=2, ),
            },

            "doctor_red_yellow": {
                "demand": _comparison_metric_presentation(doctor_cmp["demand"]),
                "uncovered": _comparison_metric_presentation(doctor_cmp["uncovered"]),
                "coverage_pct": _comparison_metric_presentation(doctor_cmp["coverage_pct"], digits=2),
            },

            "changed_base_count": comparison["fleet"]["changed_base_count"],
            "fleet_by_type": deepcopy(comparison["fleet"]["by_type"]),
            "total_cost": _comparison_metric_presentation(comparison["costs"]["total_cost"]),
        }

    # UNIT TYPES ACTUALLY PRESENT
    unit_types = set(fleet.get("by_type", {}))
    if comparison is not None:
        unit_types.update(comparison["fleet"]["by_type"])

    selected_semantics = (
        _selected_semantics(semantics, comparison_enabled=(comparison is not None), unit_types=unit_types))

    high_level_findings = (
        _build_high_level_findings(
            summary=summary,
            comparison=comparison,
            current_presentation= current_run_presentation,
            comparison_presentation=comparison_presentation,
        )
    )
    territorial_findings = (_build_territorial_findings(summary))

    # FINAL CONTROLLED PAYLOAD
    return {
        "contract": LLM_PAYLOAD_CONTRACT,
        "audience": "non_expert",
        "mode": "comparison" if comparison is not None else "single_run",
        "high_level_findings": high_level_findings,
        "territorial_findings": territorial_findings,
        "grounding": {
            "facts_source": "deterministic_118_artifacts",
            "facts_are_authoritative": True,
            "numbers_are_precomputed": True,
            "llm_must_not_recalculate_kpis": True,
            "llm_must_not_read_raw_artifacts": True,
        },

        "facts": {
            "current_run": current_run_facts,
            "comparison": comparison_facts,
        },
        "presentation": {
            "current_run": current_run_presentation,
            "comparison": comparison_presentation,
        },
        "semantics": selected_semantics,
        "instructions": [
            (
                "Spiega i risultati in italiano con linguaggio semplice e comprensibile "
                "a chi non conosce l'ottimizzazione dei servizi di emergenza."
            ),
            (
                "Usa esclusivamente i fatti e i dati contenuti nel payload. Non aggiungere numeri, cause "
                "o informazioni non presenti."
            ),
            (
                "Non ricalcolare KPI, percentuali, delta "
                "o costi. I valori sono già stati calcolati deterministicamente."
            ),
            (
                "Quando possibile, usa i valori presenti  nella sezione presentation per rendere "
                "i numeri più comprensibili."
            ),
            (
                "Per esempio, se covered_requests_per_100_approx è 96, "
                "puoi dire 'circa 96 richieste su 100'."
            ),
            (
                "Spiega le sigle tecniche la prima volta che vengono utilizzate, usando il "
                "glossario semantics."
            ),
            (
                "Distingui sempre domanda totale, domanda coperta e domanda non coperta."
            ),
            (
                "La copertura medica doctor_red_yellow riguarda esclusivamente i codici "
                "ROSSO e GIALLO."
            ),
            (
                "Se severity_source è population_health, non dire che Population Health ha "
                "modificato i codici di emergenza."
            ),
            (
                "La pesatura Population Health modifica solo la distribuzione territoriale "
                "utilizzata dall'ottimizzatore."
            ),
            (
                "Nel confronto Originale vs Population Health, descrivi le differenze "
                "come risposta dell'ottimizzatore a una diversa pesatura territoriale."
            ),
            (
                "Non descrivere le differenze tra i run come effetti causali."
            ),
            (
                "Un aumento della domanda pesata non deve essere descritto come un aumento reale "
                "del numero di chiamate avvenute."
            ),
            (
                "Non affermare che una soluzione è 'migliore' o 'peggiore' in assoluto. "
                "Descrivi invece quali indicatori migliorano o peggiorano."
            ),
            (
                "Non formulare raccomandazioni cliniche o mediche."
            ),
            (
                "Se un dato è nullo o assente, dichiaralo "
                "come non disponibile senza stimarlo."
            ),
            (
                "Preferisci frasi brevi. Prima descrivi il risultato generale, poi i principali "
                "cambiamenti e infine le criticità territoriali rilevanti."
            ),
        ],
    }
