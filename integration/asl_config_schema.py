from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# ============================================================
# CONSTANTS
# ============================================================

EMERGENCY_CODES = (
    "ROSSO",
    "GIALLO",
    "VERDE",
    "BIANCO",
)

BUDGET_MODES = (
    "purchase",
    "all",
)

PSAUT_RELOCATION_MODES = (
    "off",
    "on",
)

AUTO_MED_TRANSPORT_MODES = (
    "off",
    "base",
    "global",
)

OBJECTIVES = (
    "min_cost",
    "max_cover_budget",
)

FULL_COVERAGE_MODES = (
    "off",
    "strict",
    "feasible-only",
)

DOCTOR_COVER_MODES = (
    "off",
    "strict",
    "feasible-only",
)


# ============================================================
# PARAMETER DESCRIPTION
# ============================================================

@dataclass(frozen=True)
class ASLParameterSpec:
    key: str
    label: str
    description: str
    kind: str

    nullable: bool = False

    minimum: float | None = None
    maximum: float | None = None

    choices: tuple[str, ...] | None = None


# ============================================================
# CHATBOT WHITELIST
# ============================================================

ASL_PARAMETER_SCHEMA: dict[str, ASLParameterSpec,] = {

    # --------------------------------------------------------
    # RESPONSE THRESHOLDS
    # --------------------------------------------------------

    "T": ASLParameterSpec(
        key="T",
        label="Soglie di risposta",
        description="Tempo massimo di risposta in minuti per codice.",
        kind="threshold_map",
        minimum=0,
        maximum=60,
    ),

    # --------------------------------------------------------
    # HUMAN RESOURCES
    # --------------------------------------------------------

    "doctors_total": ASLParameterSpec(
        key="doctors_total",
        label="Medici disponibili",
        description="Numero totale di medici disponibili per la pianificazione.",
        kind="integer",
        minimum=0,
    ),

    "nurses_total": ASLParameterSpec(
        key="nurses_total",
        label="Infermieri disponibili",
        description="Numero totale di infermieri disponibili per la pianificazione.",
        kind="integer",
        minimum=0,
    ),

    "doctor_codes": ASLParameterSpec(
        key="doctor_codes",
        label="Codici con copertura medica",
        description="Codici di priorità per i quali deve essere considerata la copertura con medico.",
        kind="emergency_code_list",
    ),

    "doctor_cover": ASLParameterSpec(
        key="doctor_cover",
        label="Modalità copertura medica",
        description=(
            "Modalità con cui viene imposto "
            "il vincolo di copertura medica."
        ),
        kind="enum",
        choices=DOCTOR_COVER_MODES,
    ),

    # --------------------------------------------------------
    # BUDGET
    # --------------------------------------------------------

    "budget_total": ASLParameterSpec(
        key="budget_total",
        label="Budget totale",
        description=(
            "Budget massimo disponibile per "
            "la pianificazione."
        ),
        kind="number",
        nullable=True,
        minimum=0,
    ),

    "budget_mode": ASLParameterSpec(
        key="budget_mode",
        label="Componenti del budget",
        description=(
            "Definisce se il budget considera "
            "solo gli acquisti oppure tutti i costi."
        ),
        kind="enum",
        choices=BUDGET_MODES,
    ),

    # --------------------------------------------------------
    # PSAUT
    # --------------------------------------------------------

    "psaut_min": ASLParameterSpec(
        key="psaut_min",
        label="Numero minimo PSAUT",
        description=(
            "Numero minimo di PSAUT da mantenere."
        ),
        kind="integer",
        minimum=0,
    ),

    "psaut_exact": ASLParameterSpec(
        key="psaut_exact",
        label="Numero esatto PSAUT",
        description=(
            "Numero esatto di PSAUT richiesto, "
            "quando il vincolo è specificato."
        ),
        kind="integer",
        nullable=True,
        minimum=0,
    ),

    "reloc_psaut": ASLParameterSpec(
        key="reloc_psaut",
        label="Rilocazione PSAUT",
        description=(
            "Permette oppure impedisce "
            "la rilocazione dei PSAUT."
        ),
        kind="enum",
        choices=PSAUT_RELOCATION_MODES,
    ),

    # --------------------------------------------------------
    # AUTOMEDICA / SUPPORT VEHICLE
    # --------------------------------------------------------

    "auto_med_transport": ASLParameterSpec(
        key="auto_med_transport",
        label="Vincolo automedica-ambulanza",
        description=(
            "Definisce il vincolo di supporto "
            "tra automedica e ambulanza."
        ),
        kind="enum",
        choices=AUTO_MED_TRANSPORT_MODES,
    ),

    # --------------------------------------------------------
    # OPTIMIZATION OBJECTIVE
    # --------------------------------------------------------

    "objective": ASLParameterSpec(
        key="objective",
        label="Obiettivo di ottimizzazione",
        description=(
            "Obiettivo utilizzato dall'ottimizzatore 118."
        ),
        kind="enum",
        choices=OBJECTIVES,
    ),

    # --------------------------------------------------------
    # COVERAGE
    # --------------------------------------------------------

    "full_coverage": ASLParameterSpec(
        key="full_coverage",
        label="Copertura territoriale",
        description=(
            "Modalità generale del vincolo "
            "di copertura."
        ),
        kind="enum",
        choices=FULL_COVERAGE_MODES,
    ),
}


# ============================================================
# ERRORS
# ============================================================

@dataclass(frozen=True)
class ASLConfigValidationIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ASLConfigValidationResult:
    valid: bool
    configuration: dict[str, Any]
    errors: tuple[ASLConfigValidationIssue, ...]


class ASLConfigValidationError(
    ValueError
):
    pass


# ============================================================
# BASIC VALIDATORS
# ============================================================

def _is_number(value: Any, ) -> bool:
    return (
            isinstance(
                value,
                (int, float),
            )
            and not isinstance(
        value,
        bool,
    )
    )


def _validate_number(*, field: str, value: Any, spec: ASLParameterSpec, integer: bool, ) -> tuple[
    Any, ASLConfigValidationIssue | None]:
    if value is None and spec.nullable:
        return None, None

    if integer:
        if (not isinstance(value, int, ) or isinstance(value,bool,)):
            return None, ASLConfigValidationIssue(
                field=field,
                code="invalid_type",
                message=(
                    f"{spec.label}: "
                    "è richiesto un numero intero."
                ),
            )

    else:

        if not _is_number(value):
            return None, ASLConfigValidationIssue(
                field=field,
                code="invalid_type",
                message=(
                    f"{spec.label}: "
                    "è richiesto un valore numerico."
                ),
            )

    numeric_value = (
        int(value)
        if integer
        else float(value)
    )

    if spec.minimum is not None and numeric_value < spec.minimum:
        return None, ASLConfigValidationIssue(
            field=field,
            code="below_minimum",
            message=(
                f"{spec.label}: "
                f"il valore minimo è "
                f"{spec.minimum}."
            ),
        )

    if (spec.maximum is not None and numeric_value > spec.maximum):
        return None, ASLConfigValidationIssue(
            field=field,
            code="above_maximum",
            message=(
                f"{spec.label}: "
                f"il valore massimo è "
                f"{spec.maximum}."
            ),
        )

    return numeric_value, None


# ============================================================
# THRESHOLD VALIDATION
# ============================================================

def _validate_thresholds(
        value: Any,
) -> tuple[
    dict[str, int] | None,
    list[ASLConfigValidationIssue],
]:
    errors: list[
        ASLConfigValidationIssue
    ] = []

    if not isinstance(
            value,
            Mapping,
    ):
        errors.append(
            ASLConfigValidationIssue(
                field="T",
                code="invalid_type",
                message=(
                    "Le soglie T devono essere "
                    "un oggetto codice → minuti."
                ),
            )
        )

        return None, errors

    normalized: dict[
        str,
        int,
    ] = {}

    for raw_code, raw_value in value.items():

        code = (
            str(raw_code)
            .strip()
            .upper()
        )

        if code not in EMERGENCY_CODES:
            errors.append(
                ASLConfigValidationIssue(
                    field=f"T.{raw_code}",
                    code="unknown_emergency_code",
                    message=(
                        f"Codice di priorità "
                        f"non riconosciuto: "
                        f"{raw_code}."
                    ),
                )
            )

            continue

        if (
                not isinstance(
                    raw_value,
                    int,
                )
                or isinstance(
            raw_value,
            bool,
        )
        ):
            errors.append(
                ASLConfigValidationIssue(
                    field=f"T.{code}",
                    code="invalid_type",
                    message=(
                        f"La soglia per {code} "
                        "deve essere un numero "
                        "intero di minuti."
                    ),
                )
            )

            continue

        if not 0 <= raw_value <= 60:
            errors.append(
                ASLConfigValidationIssue(
                    field=f"T.{code}",
                    code="out_of_range",
                    message=(
                        f"La soglia per {code} "
                        "deve essere compresa "
                        "tra 0 e 60 minuti."
                    ),
                )
            )

            continue

        normalized[
            code
        ] = int(
            raw_value
        )

    return normalized, errors


# ============================================================
# DOCTOR CODE VALIDATION
# ============================================================

def _validate_doctor_codes(
        value: Any,
) -> tuple[
    list[str] | None,
    list[ASLConfigValidationIssue],
]:
    errors: list[
        ASLConfigValidationIssue
    ] = []

    if not isinstance(
            value,
            (list, tuple),
    ):
        errors.append(
            ASLConfigValidationIssue(
                field="doctor_codes",
                code="invalid_type",
                message=(
                    "doctor_codes deve essere "
                    "una lista di codici."
                ),
            )
        )

        return None, errors

    normalized: list[str] = []

    for raw_code in value:

        code = (
            str(raw_code)
            .strip()
            .upper()
        )

        if code not in EMERGENCY_CODES:
            errors.append(
                ASLConfigValidationIssue(
                    field="doctor_codes",
                    code="unknown_emergency_code",
                    message=(
                        f"Codice non riconosciuto: "
                        f"{raw_code}."
                    ),
                )
            )

            continue

        if code not in normalized:
            normalized.append(
                code
            )

    return normalized, errors


# ============================================================
# ENUM VALIDATION
# ============================================================

def _validate_enum(
        *,
        field: str,
        value: Any,
        spec: ASLParameterSpec,
) -> tuple[
    str | None,
    ASLConfigValidationIssue | None,
]:
    if (
            value is None
            and spec.nullable
    ):
        return None, None

    if not isinstance(
            value,
            str,
    ):
        return None, ASLConfigValidationIssue(
            field=field,
            code="invalid_type",
            message=(
                f"{spec.label}: "
                "è richiesto un valore testuale."
            ),
        )

    normalized = (
        value
        .strip()
        .lower()
    )

    if (
            spec.choices is not None
            and normalized
            not in spec.choices
    ):
        return None, ASLConfigValidationIssue(
            field=field,
            code="invalid_choice",
            message=(
                    f"{spec.label}: "
                    f"valore '{value}' non valido. "
                    "Valori ammessi: "
                    + ", ".join(
                spec.choices
            )
                    + "."
            ),
        )

    return normalized, None


# ============================================================
# COMPLETE CONFIG VALIDATION
# ============================================================

def validate_asl_config(
        payload: Mapping[str, Any],
        *,
        allow_empty: bool = False,
) -> ASLConfigValidationResult:
    """
    Valida una PATCH di configurazione ASL proposta
    dal chatbot.

    IMPORTANTE:
    il payload può essere parziale.

    I campi non presenti NON vengono inventati e
    non vengono sostituiti con default.
    """

    errors: list[
        ASLConfigValidationIssue
    ] = []

    normalized: dict[
        str,
        Any,
    ] = {}

    if not isinstance(
            payload,
            Mapping,
    ):
        return ASLConfigValidationResult(
            valid=False,
            configuration={},
            errors=(
                ASLConfigValidationIssue(
                    field="$",
                    code="invalid_payload",
                    message=(
                        "La configurazione deve "
                        "essere un oggetto JSON."
                    ),
                ),
            ),
        )

    # --------------------------------------------------------
    # EMPTY PATCH
    # --------------------------------------------------------

    if (
            not payload
            and not allow_empty
    ):
        errors.append(
            ASLConfigValidationIssue(
                field="$",
                code="empty_configuration",
                message=(
                    "La proposta non contiene "
                    "parametri ASL da modificare."
                ),
            )
        )

    # --------------------------------------------------------
    # UNKNOWN PARAMETERS
    # --------------------------------------------------------

    for field in payload:

        if (
                field
                not in ASL_PARAMETER_SCHEMA
        ):
            errors.append(
                ASLConfigValidationIssue(
                    field=str(field),
                    code="parameter_not_allowed",
                    message=(
                        f"Il parametro '{field}' "
                        "non è autorizzato "
                        "per il chatbot ASL."
                    ),
                )
            )

    # --------------------------------------------------------
    # ALLOWED PARAMETERS
    # --------------------------------------------------------

    for field, value in payload.items():

        spec = (
            ASL_PARAMETER_SCHEMA.get(
                field
            )
        )

        if spec is None:
            continue

        # T
        if spec.kind == "threshold_map":

            result, field_errors = (
                _validate_thresholds(
                    value
                )
            )

            errors.extend(
                field_errors
            )

            if not field_errors:
                normalized[
                    field
                ] = result

            continue

        # DOCTOR CODES
        if (
                spec.kind
                == "emergency_code_list"
        ):

            result, field_errors = (
                _validate_doctor_codes(
                    value
                )
            )

            errors.extend(
                field_errors
            )

            if not field_errors:
                normalized[
                    field
                ] = result

            continue

        # INTEGER
        if spec.kind == "integer":

            result, error = (
                _validate_number(
                    field=field,
                    value=value,
                    spec=spec,
                    integer=True,
                )
            )

            if error:

                errors.append(
                    error
                )

            else:

                normalized[
                    field
                ] = result

            continue

        # NUMBER
        if spec.kind == "number":

            result, error = (
                _validate_number(
                    field=field,
                    value=value,
                    spec=spec,
                    integer=False,
                )
            )

            if error:

                errors.append(
                    error
                )

            else:

                normalized[
                    field
                ] = result

            continue

        # ENUM
        if spec.kind == "enum":

            result, error = (
                _validate_enum(
                    field=field,
                    value=value,
                    spec=spec,
                )
            )

            if error:

                errors.append(
                    error
                )

            else:

                normalized[
                    field
                ] = result

            continue

        errors.append(
            ASLConfigValidationIssue(
                field=field,
                code="unsupported_schema_type",
                message=(
                    f"Tipo di schema non "
                    f"supportato per {field}."
                ),
            )
        )

    # ========================================================
    # CROSS-FIELD VALIDATION
    # ========================================================

    psaut_min = (
        normalized.get(
            "psaut_min"
        )
    )

    psaut_exact = (
        normalized.get(
            "psaut_exact"
        )
    )

    if (
            psaut_min is not None
            and psaut_exact is not None
            and psaut_exact < psaut_min
    ):
        errors.append(
            ASLConfigValidationIssue(
                field="psaut_exact",
                code="inconsistent_psaut_constraints",
                message=(
                    "Il numero esatto di PSAUT "
                    "non può essere inferiore "
                    "al minimo richiesto."
                ),
            )
        )

    return ASLConfigValidationResult(
        valid=not errors,
        configuration=(
            normalized
            if not errors
            else {}
        ),
        errors=tuple(
            errors
        ),
    )


# ============================================================
# LLM CONTRACT
# ============================================================

def get_asl_parameter_contract() -> dict[str, Any]:
    """
    Restituisce una descrizione serializzabile
    della whitelist.

    In seguito questa struttura verrà utilizzata
    anche per costruire il prompt del chatbot.
    """

    contract = {}

    for key, spec in (
            ASL_PARAMETER_SCHEMA.items()
    ):
        contract[
            key
        ] = {
            "label":
                spec.label,

            "description":
                spec.description,

            "type":
                spec.kind,

            "nullable":
                spec.nullable,

            "minimum":
                spec.minimum,

            "maximum":
                spec.maximum,

            "choices":
                list(
                    spec.choices
                )
                if spec.choices
                   is not None
                else None,
        }

    return contract


__all__ = [
    "ASLConfigValidationError",
    "ASLConfigValidationIssue",
    "ASLConfigValidationResult",
    "ASLParameterSpec",

    "ASL_PARAMETER_SCHEMA",

    "EMERGENCY_CODES",
    "BUDGET_MODES",
    "PSAUT_RELOCATION_MODES",
    "AUTO_MED_TRANSPORT_MODES",
    "OBJECTIVES",
    "FULL_COVERAGE_MODES",
    "DOCTOR_COVER_MODES",

    "validate_asl_config",
    "get_asl_parameter_contract",
]
