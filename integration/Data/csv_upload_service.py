from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .compatibility_report import (
    build_patient_csv_compatibility_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

UPLOAD_ROOT = (
    PROJECT_ROOT
    / "outputs"
    / "patient_csv_uploads"
)

MUNICIPALITY_CATALOG_PATH = (
    PROJECT_ROOT
    / "Ambulanze-main"
    / "AmbulanzeASL"
    / "dataset"
    / "data"
    / "comuni_geocoded.csv"
)

POSTAL_CATALOG_PATH = (
    PROJECT_ROOT
    / "integration"
    / "Data"
    / "Geography"
    / "benevento_postal_codes.csv"
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

UPLOAD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class PatientCsvUploadError(ValueError):
    pass


def _safe_original_filename(filename: str,) -> str:

    name = Path(str(filename or "")).name.strip()

    if not name:
        raise PatientCsvUploadError("Nome file mancante.")

    if Path(name).suffix.lower() != ".csv":
        raise PatientCsvUploadError("È consentito esclusivamente il caricamento di file CSV.")
    return name


def validate_and_stage_patient_csv(
    *,
    original_filename: str,
    content: bytes,
) -> dict[str, Any]:
    """
    Valida un CSV caricato dalla UI.
    Un file compatibile viene conservato in staging e associato a un upload_id opaco.
    Un file incompatibile viene eliminato dopo la validazione e NON può essere eseguito.
    """

    safe_filename = _safe_original_filename(original_filename)

    if not content:
        raise PatientCsvUploadError("Il file CSV è vuoto.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise PatientCsvUploadError("Il file CSV supera la dimensione massima consentita di 20 MB.")

    upload_id = uuid.uuid4().hex
    upload_directory = (UPLOAD_ROOT / upload_id)

    upload_directory.mkdir(parents=True, exist_ok=False)
    csv_path = (upload_directory / "patients.csv")

    try:
        csv_path.write_bytes(content)
        report = (build_patient_csv_compatibility_report(csv_path, municipality_catalog_path= MUNICIPALITY_CATALOG_PATH, postal_catalog_path= POSTAL_CATALOG_PATH))

        # Manteniamo nella risposta il nome originale mostrato all'utente.
        report["file"]["name"] = safe_filename
        compatible = bool(report.get("can_run", False))

        if not compatible:
            shutil.rmtree(upload_directory, ignore_errors=True)

            return {
                "upload_id": None,
                "stored": False,
                "report": report,
            }

        metadata = {
            "upload_id": upload_id,
            "original_filename": safe_filename,
            "contract_version": report.get("contract_version"),
            "patient_count": report.get("dataset", {},).get("patient_count"),
            "compatible": True,
        }

        (upload_directory / "upload_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8",)
        (upload_directory / "compatibility_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",)

        return {
            "upload_id": upload_id,
            "stored": True,
            "report": report,
        }

    except Exception:
        shutil.rmtree(upload_directory, ignore_errors=True)
        raise


def resolve_staged_patient_csv(upload_id: str,) -> Path:
    """
    Risolve in sicurezza un upload già validato.
    Verrà utilizzato successivamente dal real cohort adapter; nessun path arbitrario arriva dal browser.
    """

    upload_id = str(upload_id or "").strip().lower()
    if not UPLOAD_ID_PATTERN.fullmatch(
        upload_id
    ):
        raise PatientCsvUploadError("upload_id non valido.")

    path = (UPLOAD_ROOT / upload_id / "patients.csv")
    if not path.is_file():
        raise PatientCsvUploadError("Dataset caricato non trovato o non più disponibile.")

    return path


__all__ = [
    "MAX_UPLOAD_BYTES",
    "PatientCsvUploadError",
    "validate_and_stage_patient_csv",
    "resolve_staged_patient_csv",
]