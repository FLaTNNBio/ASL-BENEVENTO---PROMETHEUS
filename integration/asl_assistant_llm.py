from __future__ import annotations

import json
import os
import re

from typing import Literal

from ollama import (
    Client,
    RequestError,
    ResponseError,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
)

from .asl_config_schema import (
    get_asl_parameter_contract,
)


# ============================================================
# ERRORS
# ============================================================

class ASLAssistantLLMUnavailableError(RuntimeError):
    pass


class ASLAssistantInterpretationError(RuntimeError):
    pass


# ============================================================
# STRUCTURED OUTPUT SCHEMA
# ============================================================

EmergencyCode = Literal[
    "ROSSO",
    "GIALLO",
    "VERDE",
    "BIANCO",
]


class ThresholdPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ROSSO: int | None = None
    GIALLO: int | None = None
    VERDE: int | None = None
    BIANCO: int | None = None


class ASLConfigurationPatch(BaseModel):
    """
    PATCH parziale della configurazione ASL.

    Contiene solo i parametri che l'utente
    ha effettivamente chiesto di modificare.
    """

    model_config = ConfigDict(extra="forbid")
    T: ThresholdPatch | None = None
    doctors_total: int | None = None
    nurses_total: int | None = None

    doctor_codes: (list[EmergencyCode] | None) = None
    doctor_cover: Literal["off", "strict", "feasible-only"] | None = None
    budget_total: float | None = None
    budget_mode: Literal["purchase", "all"] | None = None
    psaut_min: int | None = None
    psaut_exact: int | None = None

    reloc_psaut: Literal["off", "on"] | None = None
    auto_med_transport: Literal["off", "base", "global"] | None = None
    objective: Literal["min_cost", "max_cover_budget"] | None = None
    full_coverage: Literal["off", "strict", "feasible-only"] | None = None


class ASLInterpretation(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    assistant_message: str

    needs_clarification: bool = False

    clarification_question: (
        str | None
    ) = None

    unsupported_requests: list[str] = (
        Field(
            default_factory=list
        )
    )

    configuration: ASLConfigurationPatch = (
        Field(
            default_factory=
                ASLConfigurationPatch
        )
    )


# ============================================================
# SYSTEM PROMPT
# ============================================================

def _build_system_prompt() -> str:

    contract = (
        get_asl_parameter_contract()
    )

    schema = (
        ASLInterpretation
        .model_json_schema()
    )

    return f"""
Sei un assistente per la configurazione
operativa del servizio di emergenza 118
dell'ASL.

Devi interpretare la richiesta dell'utente
e produrre esclusivamente una PATCH dei
parametri ASL autorizzati.

PARAMETRI AUTORIZZATI:

{json.dumps(
    contract,
    ensure_ascii=False,
    indent=2,
)}

SCHEMA DI OUTPUT:

{json.dumps(
    schema,
    ensure_ascii=False,
    indent=2,
)}

REGOLE OBBLIGATORIE:

1. Inserisci nella configurazione SOLO i
   parametri che l'utente ha realmente chiesto
   di impostare o modificare.

2. Non inventare mai valori mancanti.

3. Se l'utente specifica soltanto alcune soglie,
   restituisci soltanto quelle soglie.
   Esempio:
   "rosso 8 minuti"
   deve produrre soltanto:
   T.ROSSO = 8.

4. Non inserire automaticamente VERDE,
   BIANCO o altri valori non richiesti.

5. Non modificare parametri che non fanno
   parte del contratto ASL.

6. Non modificare parametri relativi a:
   PROMETHEUS,
   Population Health,
   seed,
   causal ranking,
   calibration,
   allocation,
   DM77,
   scenari scientifici.

7. Se l'utente richiede uno di questi elementi,
   inserisci una descrizione breve della richiesta
   in unsupported_requests.

8. Se la richiesta è ambigua e non è possibile
   determinare con sicurezza il valore o il
   parametro corretto:
   needs_clarification = true
   e formula una domanda breve.

9. Non trasformare una richiesta vaga in un
   numero arbitrario.

10. Converti correttamente gli importi.
    Esempio:
    "3 milioni di euro" = 3000000.

11. configuration è una PATCH.
    Non è la configurazione completa.

12. assistant_message deve essere breve,
    chiaro e in italiano.

13. Non spiegare il JSON.
    Rispetta rigorosamente lo schema fornito.
14. ATTENZIONE AI NUMERI:
    associa ogni numero esclusivamente al concetto
    linguistico a cui è collegato.

    ESEMPIO:

    Richiesta:
    "Dispongo di 10 medici e 17 infermieri.
    Il budget massimo è di 3 milioni.
    Vorrei i codici rossi entro 5 minuti."

    Interpretazione corretta:

    doctors_total = 10
    nurses_total = 17
    budget_total = 3000000
    T.ROSSO = 5

    NON impostare psaut_min = 5.

15. Un parametro PSAUT può essere restituito
    esclusivamente quando l'utente cita
    esplicitamente PSAUT.
""".strip()


# ============================================================
# PATCH CONVERSION
# ============================================================

def _configuration_to_patch(
    configuration: ASLConfigurationPatch,
) -> dict:

    patch = (
        configuration
        .model_dump(
            exclude_none=True
        )
    )

    if (
        "T" in patch
        and not patch["T"]
    ):
        patch.pop(
            "T"
        )

    return patch


# ============================================================
# OLLAMA CLIENT
# ============================================================

def _get_client() -> Client:

    host = os.getenv(
        "ASL_ASSISTANT_OLLAMA_HOST",
        "http://127.0.0.1:11434",
    )

    return Client(
        host=host
    )

# ============================================================
# DETERMINISTIC GROUNDING
# ============================================================

EMERGENCY_CODE_PATTERNS = {
    "ROSSO": r"\bross(?:o|i)\b",
    "GIALLO": r"\bgiall(?:o|i)\b",
    "VERDE": r"\bverd(?:e|i)\b",
    "BIANCO": r"\bbianc(?:o|hi)\b",
}


def _extract_explicit_thresholds(
    message: str,
) -> dict[str, int]:
    """
    Estrae soltanto soglie esplicite e
    inequivocabili dal testo.

    Esempio:
    'codici rossi entro 5 minuti'
        -> {"ROSSO": 5}

    Non interpreta richieste vaghe come:
    'vorrei i rossi più rapidi'.
    """

    thresholds: dict[str, int] = {}

    text = str(
        message or ""
    )


    for code, color_pattern in (
        EMERGENCY_CODE_PATTERNS.items()
    ):

        pattern = (
            color_pattern
            + r"[^.!?;\n]{0,50}?"
            + r"\b(\d{1,2})\s*"
            + r"(?:minuti?|min)\b"
        )


        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )


        if not match:
            continue


        minutes = int(
            match.group(1)
        )


        # Lo schema ASL permette 0-60.
        if 0 <= minutes <= 60:

            thresholds[
                code
            ] = minutes


    return thresholds


def _contains_psaut_reference(
    message: str,
) -> bool:

    return bool(
        re.search(
            r"\bpsaut\b",
            str(message or ""),
            flags=re.IGNORECASE,
        )
    )


def _ground_configuration_patch(
    *,
    message: str,
    patch: dict,
) -> dict:
    """
    Applica controlli deterministici alla PATCH LLM.

    Il modello interpreta il linguaggio naturale,
    ma non può introdurre campi privi di evidenza
    testuale quando questi sono facilmente
    verificabili.
    """

    grounded = dict(
        patch
    )


    # --------------------------------------------------------
    # PSAUT
    # --------------------------------------------------------
    #
    # Se l'utente non ha mai citato PSAUT,
    # il modello non può inventare parametri PSAUT.
    #

    if not _contains_psaut_reference(
        message
    ):

        grounded.pop(
            "psaut_min",
            None,
        )

        grounded.pop(
            "psaut_exact",
            None,
        )

        grounded.pop(
            "reloc_psaut",
            None,
        )


    # --------------------------------------------------------
    # EMERGENCY THRESHOLDS
    # --------------------------------------------------------
    #
    # Le soglie numeriche esplicite estratte
    # deterministicamente sono autoritative.
    #

    explicit_thresholds = (
        _extract_explicit_thresholds(
            message
        )
    )


    if explicit_thresholds:

        grounded[
            "T"
        ] = explicit_thresholds


    # --------------------------------------------------------
    # BUDGET MODE
    # --------------------------------------------------------
    #
    # budget_mode può essere impostato soltanto
    # quando l'utente specifica esplicitamente
    # quali componenti del costo devono rientrare
    # nel budget.
    #

    text = (
        str(message or "")
        .casefold()
    )


    purchase_only_patterns = (
        "solo acquisti",
        "solo gli acquisti",
        "soli acquisti",
        "costi di acquisto",
        "solo costo di acquisto",
    )


    all_cost_patterns = (
        "tutti i costi",
        "costi complessivi",
        "costo complessivo",
        "acquisti e costi operativi",
        "acquisto e gestione",
        "costi di acquisto e gestione",
    )


    if any(
        expression in text
        for expression
        in purchase_only_patterns
    ):

        grounded[
            "budget_mode"
        ] = "purchase"


    elif any(
        expression in text
        for expression
        in all_cost_patterns
    ):

        grounded[
            "budget_mode"
        ] = "all"


    else:

        grounded.pop(
            "budget_mode",
            None,
        )
    return grounded


# ============================================================
# INTERPRET USER MESSAGE
# ============================================================

def interpret_asl_message(
    *,
    message: str,
    current_configuration: dict | None = None,
) -> dict:

    # ========================================================
    # INPUT MESSAGE
    # ========================================================

    message = str(
        message or ""
    ).strip()


    if not message:

        raise ASLAssistantInterpretationError(
            "Il messaggio è vuoto."
        )


    # ========================================================
    # MODEL
    # ========================================================

    model = os.getenv(
        "ASL_ASSISTANT_MODEL",
        "llama3.2:3b",
    )


    # ========================================================
    # CURRENT CONFIGURATION
    # ========================================================

    current_configuration = (
        current_configuration
        if isinstance(
            current_configuration,
            dict,
        )
        else {}
    )


    # ========================================================
    # USER CONTEXT
    # ========================================================

    user_context = f"""
CONFIGURAZIONE ASL ATTUALMENTE APPROVATA:

{json.dumps(
    current_configuration,
    ensure_ascii=False,
    indent=2,
)}

NUOVA RICHIESTA DELL'UTENTE:

{message}

Interpreta esclusivamente la nuova richiesta.

La configurazione corrente serve soltanto
come contesto.

Nella PATCH restituisci esclusivamente
i parametri che devono cambiare.
""".strip()


    # ========================================================
    # BUILD SYSTEM PROMPT
    # ========================================================
    #
    # IMPORTANTE:
    # lo costruiamo FUORI dal try di Ollama.
    #
    # Se qui c'è un bug Python, vogliamo vederlo
    # chiaramente e non trasformarlo erroneamente
    # in "Ollama non disponibile".
    #

    system_prompt = (_build_system_prompt())

    # OLLAMA CLIENT
    client = _get_client()

    # LLM CALL
    try:
        response = client.chat(model=model,

            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },

                {
                    "role":
                        "user",

                    "content":
                        user_context,
                },
            ],

            format=(
                ASLInterpretation
                .model_json_schema()
            ),

            options={
                "temperature": 0,
            },
        )


    except RequestError as exc:

        raise ASLAssistantLLMUnavailableError(
            "Impossibile comunicare con "
            "il servizio Ollama locale."
        ) from exc


    except ResponseError as exc:

        raise ASLAssistantInterpretationError(
            "Ollama non è riuscito a "
            "completare la richiesta."
        ) from exc


    # ========================================================
    # RESPONSE CONTENT
    # ========================================================

    content = (
        response
        .message
        .content
    )


    if not content:

        raise ASLAssistantInterpretationError(
            "Il modello non ha restituito "
            "alcun contenuto."
        )


    # ========================================================
    # PYDANTIC VALIDATION
    # ========================================================

    try:

        parsed = (
            ASLInterpretation
            .model_validate_json(
                content
            )
        )


    except ValidationError as exc:

        raise ASLAssistantInterpretationError(
            "La risposta del modello non "
            "rispetta lo schema previsto."
        ) from exc


    # ========================================================
    # MODEL PATCH
    # ========================================================

    patch = (
        _configuration_to_patch(
            parsed.configuration
        )
    )


    # ========================================================
    # DETERMINISTIC GROUNDING
    # ========================================================
    #
    # Corregge / filtra le associazioni che possiamo
    # verificare deterministicamente dal testo:
    #
    # - soglie ROSSO/GIALLO/VERDE/BIANCO;
    # - PSAUT soltanto se esplicitamente citato;
    # - budget_mode soltanto se esplicitamente indicato.
    #

    patch = (
        _ground_configuration_patch(
            message=message,
            patch=patch,
        )
    )


    # ========================================================
    # RESULT
    # ========================================================

    return {

        "assistant_message":
            parsed.assistant_message,

        "needs_clarification":
            parsed.needs_clarification,

        "clarification_question":
            parsed.clarification_question,

        "unsupported_requests":
            list(
                parsed.unsupported_requests
            ),

        "configuration":
            patch,

        "model":
            model,

        "provider":
            "ollama_local",
    }

__all__ = [
    "ASLAssistantLLMUnavailableError",
    "ASLAssistantInterpretationError",
    "interpret_asl_message",
]