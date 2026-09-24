from __future__ import annotations

import argparse
import copy
import importlib.util
import math
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROMETHEUS_ROOT = PROJECT_ROOT / "PROMETHEUS-master"

PIPELINE_SCRIPT = (
    PROMETHEUS_ROOT
    / "src"
    / "scripts"
    / "run_pipeline.py"
)

DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "integration"
    / "config"
    / "pipeline_modified.yaml"
)


def _load_pipeline_module(script_path: Path) -> ModuleType:
    """
    Carica il run_pipeline.py canonico di PROMETHEUS
    senza eseguire il relativo main() da command line.
    """

    spec = importlib.util.spec_from_file_location(
        "_prometheus_canonical_run_pipeline",
        script_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Impossibile caricare la pipeline PROMETHEUS: "
            f"{script_path}"
        )

    module = importlib.util.module_from_spec(spec)

    sys.modules[spec.name] = module

    spec.loader.exec_module(module)

    return module


def _patch_independent_profile_audit(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """
    Correzione mirata dell'audit.

    Gli independent_profile_rankers sono baseline che vengono
    intenzionalmente allenati con:

        contrastive_weight = 0

    e con un SimilarityBatch vuoto.

    In PROMETHEUS il relativo robust_scale assume quindi NaN,
    perché la diagnostica contrastiva non è applicabile.

    Per rendere l'audit JSON standard-compliant convertiamo
    esclusivamente quel NaN in JSON null.

    Nessun altro NaN viene modificato.
    """

    patched = copy.deepcopy(payload)

    changed_profiles: list[str] = []

    variants = patched.get("variants")

    if not isinstance(variants, dict):
        return patched, changed_profiles

    independent = variants.get(
        "independent_profile_rankers"
    )

    if not isinstance(independent, dict):
        return patched, changed_profiles

    profiles = independent.get("profiles")

    if not isinstance(profiles, dict):
        return patched, changed_profiles

    for profile_id, profile_audit in profiles.items():

        if not isinstance(profile_audit, dict):
            continue

        if profile_audit.get("status") != "trained":
            continue

        if "contrastive_robust_scale" not in profile_audit:
            continue

        value = profile_audit[
            "contrastive_robust_scale"
        ]

        try:
            is_non_finite = not math.isfinite(
                float(value)
            )
        except (TypeError, ValueError):
            is_non_finite = False

        if is_non_finite:

            profile_audit[
                "contrastive_robust_scale"
            ] = None

            changed_profiles.append(
                str(profile_id)
            )

    return patched, changed_profiles


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Esegue la pipeline canonica PROMETHEUS "
            "utilizzando un compatibility layer esterno, "
            "senza modificare il repository originale."
        )
    )

    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help=(
            "Configurazione PROMETHEUS da utilizzare. "
            "Default: integration/config/"
            "pipeline_modified.yaml"
        ),
    )

    args = parser.parse_args()

    config_path = Path(args.config).resolve()

    if not PROMETHEUS_ROOT.is_dir():
        raise FileNotFoundError(
            f"Directory PROMETHEUS non trovata: "
            f"{PROMETHEUS_ROOT}"
        )

    if not PIPELINE_SCRIPT.is_file():
        raise FileNotFoundError(
            f"run_pipeline.py non trovato: "
            f"{PIPELINE_SCRIPT}"
        )

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configurazione non trovata: "
            f"{config_path}"
        )

    previous_cwd = Path.cwd()

    try:

        # pipeline.yaml contiene path relativi al repository,
        # ad esempio configs/care_catalog.yaml.
        #
        # Per questo motivo eseguiamo la pipeline con
        # PROMETHEUS-master come working directory.
        os.chdir(PROMETHEUS_ROOT)

        pipeline_module = _load_pipeline_module(
            PIPELINE_SCRIPT
        )

        original_write_json = (
            pipeline_module._write_json
        )

        def compatibility_write_json(
            path: Path,
            payload: dict[str, Any],
        ) -> None:

            if Path(path).name == (
                "profile_ranker_audit.json"
            ):

                (
                    patched_payload,
                    changed_profiles,
                ) = _patch_independent_profile_audit(
                    payload
                )

                if changed_profiles:

                    print(
                        "[PROMETHEUS compatibility] "
                        "contrastive_robust_scale: "
                        "NaN -> null per "
                        f"{len(changed_profiles)} "
                        "independent-profile baseline(s): "
                        + ", ".join(changed_profiles)
                    )

                original_write_json(
                    path,
                    patched_payload,
                )

                return

            # Tutti gli altri artifact continuano
            # a utilizzare il writer originale
            # con allow_nan=False.
            original_write_json(
                path,
                payload,
            )

        # Patch esclusivamente runtime.
        # Nessun file del repository viene modificato.
        pipeline_module._write_json = (
            compatibility_write_json
        )

        print(
            f"PROMETHEUS root: "
            f"{PROMETHEUS_ROOT}"
        )

        print(
            f"Config: "
            f"{config_path}"
        )

        print(
            "Compatibility mode: "
            "targeted audit serialization only"
        )

        output = Path(
            pipeline_module.run_pipeline(
                config_path
            )
        )

        if output.is_absolute():
            output_absolute = output
        else:
            output_absolute = (
                PROMETHEUS_ROOT / output
            )

        print(
            "PROMETHEUS artifacts: "
            f"{output_absolute.resolve()}"
        )

    finally:

        os.chdir(previous_cwd)


if __name__ == "__main__":
    main()