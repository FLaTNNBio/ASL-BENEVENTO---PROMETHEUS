from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_metadata(run_dir: Path):
    path = run_dir / "run_input_metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pick_key(row, candidates):
    keys = {str(k).lower(): k for k in row.keys()}
    for candidate in candidates:
        key = keys.get(candidate.lower())
        if key is not None:
            return key
    return None


def to_float(value):
    if value in (None, ""):
        return None

    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def resolve_demand_file(run_dir: Path, metadata: dict):
    candidates = []

    effective = metadata.get("effective_data_dir")
    if effective:
        candidates.append(Path(effective))

    candidates.append(run_dir / "input_data")

    original = metadata.get("original_dataset_dir")
    if original:
        candidates.append(Path(original))

    for directory in candidates:
        for filename in ("weighted_demand_by_comune_code.csv", "demand_by_comune_code.csv",):
            path = directory / filename
            if path.exists():
                return path

    raise FileNotFoundError(f"Nessun demand CSV trovato per {run_dir.name}")


def aggregate_demand(path: Path):
    rows = read_csv(path)

    if not rows:
        return {}

    first = rows[0]
    comune_k = pick_key(first, ["comune", "denominazione", "nome_comune",],)
    demand_k = pick_key(first, ["n_missioni_pesate", "weighted_demand", "demand", "n_missioni", ],)
    tier_k = pick_key(first, ["severity_tier", "tier", ],)
    weight_k = pick_key(first, [ "tier_weight", "severity_weight", ],)

    if not comune_k:
        raise RuntimeError(f"Colonna comune non trovata in {path}")

    if not demand_k:
        raise RuntimeError(f"Colonna domanda non trovata in {path}")

    result = defaultdict(lambda: {"demand": 0.0, "tier": None, "weight": None, })

    for row in rows:
        comune = str(row.get(comune_k, "")).strip()
        if not comune:
            continue

        demand = to_float(
            row.get(demand_k)
        )

        if demand is not None:
            result[comune]["demand"] += demand

        if tier_k:
            tier = str(
                row.get(tier_k, "")
            ).strip().upper()

            if tier:
                result[comune]["tier"] = tier

        if weight_k:
            weight = to_float(
                row.get(weight_k)
            )

            if weight is not None:
                result[comune]["weight"] = weight

    return dict(result)


def allocation_by_base(run_dir: Path):
    path = run_dir / "chosen_slots.csv"

    if not path.exists():
        return {}

    rows = read_csv(path)

    if not rows:
        return {}

    base_k = pick_key(
        rows[0],
        [
            "base_comune",
            "base",
            "comune",
        ],
    )

    type_k = pick_key(
        rows[0],
        [
            "tipo",
            "type",
        ],
    )

    result = defaultdict(Counter)

    for row in rows:
        base = str(
            row.get(base_k, "")
            if base_k
            else ""
        ).strip()

        tipo = str(
            row.get(type_k, "")
            if type_k
            else ""
        ).strip().upper()

        if base and tipo:
            result[base][tipo] += 1

    return dict(result)


def allocation_text(counter):
    if not counter:
        return "—"

    return ", ".join(
        f"{tipo}={qty}"
        for tipo, qty
        in sorted(counter.items())
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "original_run"
    )

    parser.add_argument(
        "ph_run"
    )

    parser.add_argument(
        "--top",
        type=int,
        default=15,
    )

    args = parser.parse_args()

    original_run = Path(
        args.original_run
    ).resolve()

    ph_run = Path(
        args.ph_run
    ).resolve()

    original_meta = read_metadata(
        original_run
    )

    ph_meta = read_metadata(
        ph_run
    )

    original_demand_file = resolve_demand_file(
        original_run,
        original_meta,
    )

    ph_demand_file = resolve_demand_file(
        ph_run,
        ph_meta,
    )

    original_demand = aggregate_demand(
        original_demand_file
    )

    ph_demand = aggregate_demand(
        ph_demand_file
    )

    original_alloc = allocation_by_base(
        original_run
    )

    ph_alloc = allocation_by_base(
        ph_run
    )

    municipalities = sorted(
        set(original_demand)
        | set(ph_demand)
    )

    comparison = []

    for comune in municipalities:
        orig = original_demand.get(
            comune,
            {},
        )

        ph = ph_demand.get(
            comune,
            {},
        )

        original_value = float(
            orig.get("demand", 0.0)
        )

        ph_value = float(
            ph.get("demand", 0.0)
        )

        delta = (
            ph_value
            - original_value
        )

        delta_pct = (
            100.0
            * delta
            / original_value
            if original_value != 0
            else None
        )

        comparison.append(
            {
                "comune": comune,
                "original": original_value,
                "ph": ph_value,
                "delta": delta,
                "delta_pct": delta_pct,
                "tier": ph.get("tier"),
                "weight": ph.get("weight"),
            }
        )

    print()
    print("=" * 100)
    print(
        "IMPATTO TERRITORIALE "
        "ORIGINALE vs POPULATION HEALTH"
    )
    print("=" * 100)

    print(
        "ORIGINAL:",
        original_run.name,
    )

    print(
        "PH      :",
        ph_run.name,
    )

    print(
        "SCENARIO:",
        ph_meta.get(
            "severity_scenario_id"
        ),
    )

    print(
        "METRIC  :",
        ph_meta.get(
            "indicator"
        ),
    )

    print()
    print(
        "DEMAND ORIGINAL:",
        original_demand_file,
    )

    print(
        "DEMAND PH      :",
        ph_demand_file,
    )

    print()
    print(
        "Comuni confrontati:",
        len(comparison),
    )

    tier_counts = Counter(
        row["tier"]
        for row in comparison
        if row["tier"]
    )

    print(
        "Tier PH:",
        dict(tier_counts),
    )

    # --------------------------------------------------
    # Aumenti
    # --------------------------------------------------

    increases = sorted(
        comparison,
        key=lambda row: row["delta"],
        reverse=True,
    )

    print()
    print(
        f"TOP {args.top} AUMENTI DI DOMANDA"
    )
    print("-" * 100)

    for row in increases[:args.top]:

        pct = (
            "n.d."
            if row["delta_pct"] is None
            else f"{row['delta_pct']:+.2f}%"
        )

        print(
            f"{row['comune']:<32}"
            f" ORIG={row['original']:>9.2f}"
            f" PH={row['ph']:>9.2f}"
            f" Δ={row['delta']:>+9.2f}"
            f" ({pct:>9})"
            f" tier={str(row['tier'] or '—'):<5}"
            f" peso={row['weight'] if row['weight'] is not None else '—'}"
        )

    # --------------------------------------------------
    # Diminuzioni
    # --------------------------------------------------

    decreases = sorted(
        comparison,
        key=lambda row: row["delta"],
    )

    print()
    print(
        f"TOP {args.top} DIMINUZIONI DI DOMANDA"
    )
    print("-" * 100)

    for row in decreases[:args.top]:

        pct = (
            "n.d."
            if row["delta_pct"] is None
            else f"{row['delta_pct']:+.2f}%"
        )

        print(
            f"{row['comune']:<32}"
            f" ORIG={row['original']:>9.2f}"
            f" PH={row['ph']:>9.2f}"
            f" Δ={row['delta']:>+9.2f}"
            f" ({pct:>9})"
            f" tier={str(row['tier'] or '—'):<5}"
            f" peso={row['weight'] if row['weight'] is not None else '—'}"
        )

    # --------------------------------------------------
    # Allocazioni modificate
    # --------------------------------------------------

    print()
    print("VARIAZIONI NELL'ALLOCAZIONE")
    print("-" * 100)

    all_bases = sorted(
        set(original_alloc)
        | set(ph_alloc)
    )

    changed = 0

    for base in all_bases:

        original_counter = (
            original_alloc.get(
                base,
                Counter(),
            )
        )

        ph_counter = (
            ph_alloc.get(
                base,
                Counter(),
            )
        )

        if original_counter == ph_counter:
            continue

        changed += 1

        demand_row = next(
            (
                row
                for row in comparison
                if row["comune"] == base
            ),
            None,
        )

        if demand_row:
            severity = (
                f"tier={demand_row['tier'] or '—'} "
                f"peso={demand_row['weight'] or '—'} "
                f"Δdomanda={demand_row['delta']:+.2f}"
            )
        else:
            severity = (
                "domanda territoriale non trovata"
            )

        print()
        print(base)

        print(
            "  ORIGINAL:",
            allocation_text(
                original_counter
            ),
        )

        print(
            "  PH      :",
            allocation_text(
                ph_counter
            ),
        )

        print(
            "  ",
            severity,
        )

    if changed == 0:
        print(
            "Nessuna variazione "
            "nell'allocazione."
        )

    print()
    print(
        "Basi con allocazione modificata:",
        changed,
    )

    print("=" * 100)


if __name__ == "__main__":
    main()