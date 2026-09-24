from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def to_float(value):
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def first_value(row, candidates):
    if not row:
        return None

    keys = {
        str(key).strip().lower(): key
        for key in row.keys()
    }

    for candidate in candidates:
        original_key = keys.get(candidate.lower())

        if original_key is not None:
            value = row.get(original_key)

            if value not in (None, ""):
                return value

    return None


def read_csv(path: Path):
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        return list(
            csv.DictReader(handle)
        )


def read_metadata(run_dir: Path):
    path = (
        run_dir
        / "run_input_metadata.json"
    )

    if not path.exists():
        return {}

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def get_code(row):
    value = first_value(
        row,
        [
            "codice",
            "code",
            "CODICE",
        ],
    )

    return str(
        value or ""
    ).strip().upper()


def coverage_metrics(
    rows,
    *,
    doctor=False,
):
    if not rows:
        return {
            "calls": None,
            "uncovered": None,
            "coverage_pct": None,
        }

    # Per la copertura con medico ci interessano
    # esclusivamente ROSSO + GIALLO,
    # coerentemente con la dashboard.
    if doctor:

        rg_rows = [
            row
            for row in rows
            if get_code(row)
            in {"ROSSO", "GIALLO"}
        ]

        if rg_rows:
            rows = rg_rows

    else:

        # Se esiste una riga TOTAL, non deve essere
        # sommata insieme alle righe per codice.
        non_total = [
            row
            for row in rows
            if get_code(row) != "TOTAL"
        ]

        if non_total:
            rows = non_total

    total_calls = 0.0
    total_uncovered = 0.0
    found_calls = False
    found_uncovered = False

    for row in rows:

        calls = to_float(
            first_value(
                row,
                [
                    "chiamate",
                    "total_calls",
                    "calls",
                ],
            )
        )

        uncovered_candidates = (
            [
                "uncovered_doctor",
                "uncovered",
                "total_uncovered",
            ]
            if doctor
            else
            [
                "uncovered",
                "total_uncovered",
            ]
        )

        uncovered = to_float(
            first_value(
                row,
                uncovered_candidates,
            )
        )

        if calls is not None:
            total_calls += calls
            found_calls = True

        if uncovered is not None:
            total_uncovered += uncovered
            found_uncovered = True

    calls = (
        total_calls
        if found_calls
        else None
    )

    uncovered = (
        total_uncovered
        if found_uncovered
        else None
    )

    coverage_pct = None

    if (
        calls is not None
        and uncovered is not None
        and calls > 0
    ):
        coverage_pct = (
            100.0
            * (
                1.0
                - uncovered / calls
            )
        )

    return {
        "calls": calls,
        "uncovered": uncovered,
        "coverage_pct": coverage_pct,
    }


def chosen_summary(rows):
    by_type = Counter()
    by_base = Counter()

    for row in rows:

        tipo = str(
            first_value(
                row,
                [
                    "tipo",
                    "type",
                ],
            )
            or ""
        ).strip().upper()

        base = str(
            first_value(
                row,
                [
                    "base_comune",
                    "base",
                    "comune",
                ],
            )
            or ""
        ).strip()

        if tipo:
            by_type[tipo] += 1

        if base:
            by_base[base] += 1

    return {
        "total": len(rows),
        "by_type": by_type,
        "by_base": by_base,
    }


def fmt(value, digits=2):
    if value is None:
        return "n.d."

    return f"{value:.{digits}f}"


def delta(original, ph):
    if (
        original is None
        or ph is None
    ):
        return None

    return ph - original


def print_metric(
    label,
    original,
    ph,
    *,
    digits=2,
    suffix="",
):
    difference = delta(
        original,
        ph,
    )

    diff_text = (
        "n.d."
        if difference is None
        else (
            f"{difference:+.{digits}f}"
            f"{suffix}"
        )
    )

    print(
        f"{label:<28}"
        f" ORIGINAL={fmt(original, digits)}{suffix:<2}"
        f" PH={fmt(ph, digits)}{suffix:<2}"
        f" Δ(PH-ORIG)={diff_text}"
    )


def compare_counter(
    title,
    original,
    ph,
):
    print()
    print(title)
    print("-" * len(title))

    keys = sorted(
        set(original)
        | set(ph)
    )

    if not keys:
        print("Nessun dato.")
        return

    for key in keys:

        o = original.get(
            key,
            0,
        )

        p = ph.get(
            key,
            0,
        )

        print(
            f"{key:<25}"
            f" ORIGINAL={o:<4}"
            f" PH={p:<4}"
            f" Δ={p-o:+d}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Confronta un run 118 originale "
            "con un run Population Health."
        )
    )

    parser.add_argument(
        "original_run",
        help="Directory del run originale",
    )

    parser.add_argument(
        "ph_run",
        help="Directory del run Population Health",
    )

    args = parser.parse_args()

    original_dir = Path(
        args.original_run
    ).resolve()

    ph_dir = Path(
        args.ph_run
    ).resolve()

    if not original_dir.is_dir():
        raise SystemExit(
            f"Run originale non trovato: "
            f"{original_dir}"
        )

    if not ph_dir.is_dir():
        raise SystemExit(
            f"Run PH non trovato: "
            f"{ph_dir}"
        )

    original_meta = read_metadata(
        original_dir
    )

    ph_meta = read_metadata(
        ph_dir
    )

    print()
    print("=" * 72)
    print(
        "CONFRONTO 118 — "
        "ORIGINALE vs POPULATION HEALTH"
    )
    print("=" * 72)

    print()
    print(
        "ORIGINAL:",
        original_dir.name,
    )

    print(
        "PH      :",
        ph_dir.name,
    )

    print()

    print(
        "SOURCE ORIGINAL:",
        original_meta.get(
            "severity_source"
        ),
    )

    print(
        "SOURCE PH      :",
        ph_meta.get(
            "severity_source"
        ),
    )

    print(
        "SCENARIO PH    :",
        ph_meta.get(
            "severity_scenario_id"
        ),
    )

    print(
        "RUN PROMETHEUS :",
        ph_meta.get(
            "source_run_id"
        ),
    )

    print(
        "METRIC PH      :",
        ph_meta.get(
            "indicator"
        ),
    )

    # --------------------------------------------------
    # Coverage ANY
    # --------------------------------------------------

    original_any = coverage_metrics(
        read_csv(
            original_dir
            / "coverage_summary.csv"
        )
    )

    ph_any = coverage_metrics(
        read_csv(
            ph_dir
            / "coverage_summary.csv"
        )
    )

    # --------------------------------------------------
    # Doctor coverage ROSSO + GIALLO
    # --------------------------------------------------

    original_doc = coverage_metrics(
        read_csv(
            original_dir
            / "doctor_coverage_summary.csv"
        ),
        doctor=True,
    )

    ph_doc = coverage_metrics(
        read_csv(
            ph_dir
            / "doctor_coverage_summary.csv"
        ),
        doctor=True,
    )

    print()
    print("RISULTATI GLOBALI")
    print("-----------------")

    print_metric(
        "Domanda ANY",
        original_any["calls"],
        ph_any["calls"],
    )

    print_metric(
        "Uncovered ANY",
        original_any["uncovered"],
        ph_any["uncovered"],
    )

    print_metric(
        "Copertura ANY",
        original_any["coverage_pct"],
        ph_any["coverage_pct"],
        suffix="%",
    )

    print_metric(
        "Domanda medico R+G",
        original_doc["calls"],
        ph_doc["calls"],
    )

    print_metric(
        "Uncovered medico R+G",
        original_doc["uncovered"],
        ph_doc["uncovered"],
    )

    print_metric(
        "Copertura medico R+G",
        original_doc["coverage_pct"],
        ph_doc["coverage_pct"],
        suffix="%",
    )

    # --------------------------------------------------
    # Chosen slots
    # --------------------------------------------------

    original_chosen = chosen_summary(
        read_csv(
            original_dir
            / "chosen_slots.csv"
        )
    )

    ph_chosen = chosen_summary(
        read_csv(
            ph_dir
            / "chosen_slots.csv"
        )
    )

    print()
    print("UNITÀ ATTIVE")
    print("------------")

    print(
        "ORIGINAL:",
        original_chosen["total"],
    )

    print(
        "PH      :",
        ph_chosen["total"],
    )

    print(
        "DELTA   :",
        ph_chosen["total"]
        - original_chosen["total"],
    )

    compare_counter(
        "UNITÀ PER TIPO",
        original_chosen["by_type"],
        ph_chosen["by_type"],
    )

    compare_counter(
        "UNITÀ PER BASE",
        original_chosen["by_base"],
        ph_chosen["by_base"],
    )

    print()
    print("=" * 72)


if __name__ == "__main__":
    main()