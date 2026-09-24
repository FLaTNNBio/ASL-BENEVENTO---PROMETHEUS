from __future__ import annotations

from typing import Any, Mapping

from .asl_config_schema import (
    ASL_PARAMETER_SCHEMA,
    validate_asl_config,
)

from .asl_assistant_llm import (
    ASLAssistantInterpretationError,
    ASLAssistantLLMUnavailableError,
    interpret_asl_message,
)


class ASLAssistantRequestError(ValueError):
    """Richiesta HTTP non valida per l'assistente ASL."""
    pass


def _build_preview(
    configuration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Costruisce una preview human-readable
    dei soli parametri effettivamente proposti.
    """

    preview: list[dict[str, Any]] = []

    for key, value in configuration.items():

        spec = ASL_PARAMETER_SCHEMA[key]

        preview.append(
            {
                "key": key,
                "label": spec.label,
                "description": spec.description,
                "value": value,
            }
        )

    return preview


def validate_asl_assistant_request(
    payload: Any,
) -> dict[str, Any]:
    """
    Valida una proposta di configurazione prodotta
    dall'utente o, in seguito, dall'LLM.

    Contratto HTTP atteso:

    {
        "configuration": {
            ...
        }
    }
    """

    if not isinstance(payload, Mapping):
        raise ASLAssistantRequestError(
            "Il corpo della richiesta deve essere un oggetto JSON."
        )

    if "configuration" not in payload:
        raise ASLAssistantRequestError(
            "Campo 'configuration' mancante."
        )

    configuration = payload["configuration"]

    if not isinstance(configuration, Mapping):
        raise ASLAssistantRequestError(
            "'configuration' deve essere un oggetto JSON."
        )

    result = validate_asl_config(
        configuration,
        allow_empty=False,
    )

    if not result.valid:

        return {
            "status": "invalid",
            "valid": False,

            "configuration": {},

            "preview": [],

            "errors": [
                {
                    "field": error.field,
                    "code": error.code,
                    "message": error.message,
                }
                for error in result.errors
            ],
        }

    normalized = result.configuration

    return {
        "status": "valid",
        "valid": True,

        "configuration": normalized,

        "preview": _build_preview(
            normalized
        ),

        "errors": [],
    }

def interpret_asl_assistant_request(
    payload: Any,
) -> dict[str, Any]:

    if not isinstance(
        payload,
        Mapping,
    ):
        raise ASLAssistantRequestError(
            "Il corpo della richiesta "
            "deve essere un oggetto JSON."
        )


    message = str(
        payload.get(
            "message",
            "",
        )
    ).strip()


    if not message:

        raise ASLAssistantRequestError(
            "Campo 'message' mancante "
            "o vuoto."
        )


    current_configuration = (
        payload.get(
            "current_configuration",
            {},
        )
    )


    if not isinstance(
        current_configuration,
        Mapping,
    ):

        raise ASLAssistantRequestError(
            "'current_configuration' deve "
            "essere un oggetto JSON."
        )


    # ========================================================
    # VALIDATE CURRENT CONFIGURATION
    # ========================================================

    current_result = (
        validate_asl_config(
            current_configuration,
            allow_empty=True,
        )
    )


    if not current_result.valid:

        raise ASLAssistantRequestError(
            "La configurazione ASL corrente "
            "non è valida."
        )


    # ========================================================
    # LLM INTERPRETATION
    # ========================================================

    interpretation = (
        interpret_asl_message(
            message=message,
            current_configuration=
                current_result.configuration,
        )
    )


    # ========================================================
    # UNSUPPORTED REQUEST
    # ========================================================

    unsupported = (
        interpretation.get(
            "unsupported_requests",
            [],
        )
    )


    if unsupported:

        return {
            "status":
                "unsupported",

            "valid":
                False,

            "assistant_message":
                interpretation[
                    "assistant_message"
                ],

            "configuration": {},

            "preview": [],

            "errors": [
                {
                    "field": "$",
                    "code":
                        "unsupported_request",
                    "message":
                        request,
                }
                for request
                in unsupported
            ],
        }


    # ========================================================
    # CLARIFICATION REQUIRED
    # ========================================================

    if interpretation.get(
        "needs_clarification"
    ):

        question = (
            interpretation.get(
                "clarification_question"
            )
            or
            "Puoi specificare meglio "
            "la configurazione desiderata?"
        )


        return {
            "status":
                "clarification",

            "valid":
                False,

            "assistant_message":
                question,

            "configuration": {},

            "preview": [],

            "errors": [],
        }


    configuration = (
        interpretation.get(
            "configuration",
            {},
        )
    )


    # ========================================================
    # EMPTY PATCH
    # ========================================================

    if not configuration:

        return {
            "status":
                "clarification",

            "valid":
                False,

            "assistant_message":
                (
                    interpretation.get(
                        "assistant_message"
                    )
                    or
                    "Non ho individuato "
                    "parametri ASL espliciti "
                    "da modificare."
                ),

            "configuration": {},

            "preview": [],

            "errors": [],
        }


    # ========================================================
    # AUTHORITATIVE VALIDATION
    # ========================================================

    validation = validate_asl_config(
        configuration,
        allow_empty=False,
    )


    if not validation.valid:

        return {
            "status":
                "invalid",

            "valid":
                False,

            "assistant_message":
                (
                    "Ho interpretato la richiesta, "
                    "ma alcuni valori non superano "
                    "la validazione ASL."
                ),

            "configuration": {},

            "preview": [],

            "errors": [
                {
                    "field":
                        error.field,

                    "code":
                        error.code,

                    "message":
                        error.message,
                }
                for error
                in validation.errors
            ],
        }


    normalized = (
        validation.configuration
    )


    return {
        "status":
            "valid",

        "valid":
            True,

        "assistant_message":
            interpretation[
                "assistant_message"
            ],

        "configuration":
            normalized,

        "preview":
            _build_preview(
                normalized
            ),

        "errors": [],

        "model":
            interpretation.get(
                "model"
            ),
    }

__all__ = [
     "ASLAssistantRequestError",

    "ASLAssistantLLMUnavailableError",
    "ASLAssistantInterpretationError",

    "validate_asl_assistant_request",
    "interpret_asl_assistant_request",
]