from __future__ import annotations

import json
import math
import os
import re

from typing import Any, Mapping
from ollama import Client, RequestError, ResponseError
from pydantic import BaseModel, ConfigDict, Field, ValidationError


# ERRORS
class Run118ExplainLLMUnavailableError(RuntimeError):
    pass


class Run118ExplainLLMError(RuntimeError):
    pass


# STRUCTURED OUTPUT
class Run118Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=900)
    what_changes: list[str] = Field(default_factory=list, max_length=5)
    territorial_notes: list[str] = Field(default_factory=list, max_length=3)
    important_note: str = Field(min_length=1, max_length=500)


# OLLAMA
def _get_client() -> Client:
    host = os.getenv("ASL_ASSISTANT_OLLAMA_HOST", "http://127.0.0.1:11434")
    return Client(host=host)


def _get_model() -> str:
    return os.getenv("EXPLAIN_118_MODEL", os.getenv("ASL_ASSISTANT_MODEL", "llama3.2:3b"))


# PROMPT
def _build_system_prompt() -> str:

    schema = (Run118Explanation.model_json_schema())

    return f"""
Sei un assistente che deve RISCRIVERE in modo semplice
alcuni risultati già interpretati deterministicamente
dall'applicazione.

NON devi analizzare autonomamente i dati.

Il pubblico è una persona non esperta di:
- ottimizzazione;
- statistica;
- servizi sanitari;
- Population Health.

SCHEMA JSON OBBLIGATORIO:

{json.dumps(schema, ensure_ascii=False, indent=2)}

============================================================
FONTE PRINCIPALE
============================================================

La fonte principale della risposta è:

    high_level_findings

Queste frasi sono già state costruite
deterministicamente dall'applicazione.

Per le criticità territoriali usa esclusivamente:

    territorial_findings

Puoi usare "semantics" soltanto per capire
il significato dei termini tecnici.

============================================================
COSA DEVI FARE
============================================================

1. Riscrivi i finding in italiano naturale e semplice.

2. Mantieni ESATTAMENTE il significato dei finding.

3. Conserva i numeri presenti nei finding.

4. Puoi omettere un numero non importante,
   ma NON puoi introdurne uno nuovo.

5. Non calcolare percentuali.

6. Non trasformare valori assoluti in percentuali.

7. Non trasformare punti percentuali in percentuali.

8. Non inventare confronti relativi come:
   "5% in più",
   "10% in meno",
   se queste quantità non sono già presenti
   nei finding.

============================================================
STILE
============================================================

9. Il campo "summary" deve essere breve:
   massimo 4 frasi.

10. "what_changes" deve contenere da 2 a 5
    punti sintetici.

11. Evita ripetizioni.

12. Spiega eventuali sigle tecniche
    la prima volta che le utilizzi.

13. Preferisci:
    "domanda non coperta"

    e non:
    "uncovered demand".

14. Non descrivere una soluzione come
    migliore o peggiore in assoluto.

============================================================
POPULATION HEALTH
============================================================

15. Population Health NON modifica
    ROSSO, GIALLO, VERDE e BIANCO.

16. Population Health modifica solamente
    la pesatura territoriale della domanda
    utilizzata dall'ottimizzatore.

17. Non dire che una variazione della domanda
    pesata rappresenta nuove chiamate realmente
    avvenute.

18. Non usare formulazioni causali.

Sono vietate espressioni come:

    "Population Health ha causato..."
    "Population Health ha provocato..."
    "Population Health ha determinato..."

============================================================
TERRITORIO
============================================================

19. "territorial_notes" può contenere soltanto
    informazioni presenti in territorial_findings.

20. Non inventare Comuni o codici.

============================================================
NOTA FINALE
============================================================

21. "important_note" deve spiegare in modo semplice
    che il confronto mostra come cambia la soluzione
    quando cambia la pesatura territoriale.

22. Non descriverlo come prova di un effetto causale.

23. Non aggiungere testo fuori dal JSON.
""".strip()


def _build_user_context(payload: Mapping[str, Any]) -> str:
    controlled = {
        "mode": payload["mode"],
        "high_level_findings": payload.get("high_level_findings", []),
        "territorial_findings": payload.get("territorial_findings", []),
        "semantics":payload.get("semantics", {}),
    }

    return f"""
CONTESTO CONTROLLATO:

{json.dumps(controlled, ensure_ascii=False, indent=2)}

Scrivi una spiegazione semplice.

IMPORTANTE:
usa come fatti soltanto high_level_findings
e territorial_findings.
""".strip()


# NUMERIC GROUNDING VALIDATION
_NUMBER_PATTERN = re.compile(r"(?<![\w])[-+]?\d+(?:[.,]\d+)*")


def _parse_number(token: str) -> float | None:

    text = str(token).strip()
    if not text:
        return None
    sign = 1.0

    if text.startswith("-"):
        sign = -1.0
        text = text[1:]

    elif text.startswith("+"):
        text = text[1:]

    # Italiano:
    # 250.000,50
    if "." in text and "," in text:
        text = (text.replace(".","").replace(",", "."))

    elif "," in text:
        text = text.replace(",",".")

    elif "." in text:
        parts = text.split(".")
        # 250.000 -> migliaia
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
            text = "".join(parts)
    try:
        return sign * float(text)
    except ValueError:
        return None


def _extract_numbers(
    text: str,
) -> list[float]:

    result = []


    for token in _NUMBER_PATTERN.findall(
        text
    ):

        value = _parse_number(
            token
        )

        if value is not None:

            result.append(
                value
            )


    return result


def _finding_text(
    payload: Mapping[str, Any],
) -> str:

    pieces = []


    for key in (
        "high_level_findings",
        "territorial_findings",
    ):

        for item in payload.get(
            key,
            [],
        ):

            statement = item.get(
                "statement"
            )

            if statement:

                pieces.append(
                    str(
                        statement
                    )
                )


    return "\n".join(
        pieces
    )


def _allowed_numbers(
    payload: Mapping[str, Any],
) -> list[float]:

    # 118 è il nome del servizio,
    # non un KPI.
    allowed = [
        118.0
    ]


    allowed.extend(
        _extract_numbers(
            _finding_text(
                payload
            )
        )
    )


    return allowed


def _same_number(
    left: float,
    right: float,
) -> bool:

    return math.isclose(
        left,
        right,
        rel_tol=1e-9,
        abs_tol=1e-9,
    )


def _validate_numeric_grounding(
    *,
    explanation: Run118Explanation,
    payload: Mapping[str, Any],
) -> None:

    text = "\n".join(
        [
            explanation.title,
            explanation.summary,
            *explanation.what_changes,
            *explanation.territorial_notes,
            explanation.important_note,
        ]
    )


    generated_numbers = (
        _extract_numbers(
            text
        )
    )

    allowed = (
        _allowed_numbers(
            payload
        )
    )


    unauthorized = []


    for number in generated_numbers:

        if not any(
            _same_number(
                number,
                allowed_value,
            )
            for allowed_value
            in allowed
        ):

            unauthorized.append(
                number
            )


    if unauthorized:

        raise Run118ExplainLLMError(
            "La spiegazione contiene numeri "
            "non presenti nei finding "
            "deterministici: "
            f"{unauthorized}"
        )


# ============================================================
# SEMANTIC GUARDRAILS
# ============================================================

_FORBIDDEN_PATTERNS = (
    "population health ha causato",
    "population health ha provocato",
    "population health ha determinato",
    "population health causa",
    "population health provoca",
    "population health determina",
)

_SINGLE_RUN_COMPARISON_PATTERNS = (
    "rispetto alla pianificazione originale",
    "rispetto al run originale",
    "rispetto alla soluzione originale",
    "le differenze rispetto",
    "quando cambia la pesatura territoriale",
    "come cambia la soluzione quando cambia",
    "rispetto a population health",
)


def _validate_semantic_grounding(
    explanation: Run118Explanation,
    *,
    payload: Mapping[str, Any],
) -> None:

    text = " ".join(
        [
            explanation.title,
            explanation.summary,
            *explanation.what_changes,
            *explanation.territorial_notes,
            explanation.important_note,
        ]
    ).lower()


    # ========================================================
    # CAUSAL LANGUAGE
    # ========================================================

    for pattern in _FORBIDDEN_PATTERNS:

        if pattern in text:

            raise Run118ExplainLLMError(
                "La spiegazione contiene "
                "una formulazione causale vietata: "
                f"{pattern!r}"
            )


    # ========================================================
    # SINGLE RUN MUST NOT INVENT A COMPARISON
    # ========================================================

    if (
        payload.get(
            "mode"
        )
        == "single_run"
    ):

        for pattern in (
            _SINGLE_RUN_COMPARISON_PATTERNS
        ):

            if pattern in text:

                raise Run118ExplainLLMError(
                    "La spiegazione single_run "
                    "introduce un confronto "
                    "non presente nei dati: "
                    f"{pattern!r}"
                )

# ============================================================
# FACT COVERAGE VALIDATION
# ============================================================

def _validate_minimum_fact_coverage(
    *,
    explanation: Run118Explanation,
    payload: Mapping[str, Any],
) -> None:
    """
    Impedisce di accettare risposte formalmente corrette
    ma prive di contenuto, come:

        "Ecco i risultati del run."

    La risposta deve riportare almeno uno dei valori
    contenuti nel primo finding deterministico,
    normalmente la copertura complessiva.
    """

    findings = payload.get(
        "high_level_findings",
        [],
    )


    if not findings:

        raise Run118ExplainLLMError(
            "Nessun finding disponibile "
            "per verificare la copertura fattuale."
        )


    first_statement = str(
        findings[0].get(
            "statement",
            "",
        )
    )


    expected_numbers = [
        number

        for number
        in _extract_numbers(
            first_statement
        )

        # 100 è soltanto il denominatore
        # della formulazione "X richieste su 100".
        # Da solo non dimostra che il modello
        # abbia riportato il risultato.
        if not _same_number(
            number,
            100.0,
        )
    ]


    if not expected_numbers:

        raise Run118ExplainLLMError(
            "Il finding principale non contiene "
            "valori verificabili."
        )


    generated_text = "\n".join(
        [
            explanation.summary,
            *explanation.what_changes,
            *explanation.territorial_notes,
        ]
    )


    generated_numbers = (
        _extract_numbers(
            generated_text
        )
    )


    has_supported_fact = any(

        _same_number(
            generated,
            expected,
        )

        for generated
        in generated_numbers

        for expected
        in expected_numbers
    )


    if not has_supported_fact:

        raise Run118ExplainLLMError(
            "La spiegazione non riporta "
            "alcun risultato concreto del "
            "finding principale."
        )


    # Un confronto deve inoltre contenere
    # almeno qualche informazione esplicativa.
    if (
        payload.get(
            "mode"
        )
        == "comparison"
        and
        len(
            explanation.what_changes
        ) < 2
    ):

        raise Run118ExplainLLMError(
            "La spiegazione del confronto "
            "non contiene abbastanza "
            "cambiamenti concreti."
        )


# ============================================================
# DETERMINISTIC FALLBACK
# ============================================================

def _build_deterministic_fallback(
    payload: Mapping[str, Any],
) -> Run118Explanation:
    """
    Costruisce una spiegazione semplice direttamente
    dai finding deterministici.

    Non utilizza il modello linguistico.
    Non introduce nuovi KPI.
    """

    high_level = [
        str(
            item.get(
                "statement",
                "",
            )
        ).strip()

        for item
        in payload.get(
            "high_level_findings",
            [],
        )

        if str(
            item.get(
                "statement",
                "",
            )
        ).strip()
    ]


    territorial = [
        str(
            item.get(
                "statement",
                "",
            )
        ).strip()

        for item
        in payload.get(
            "territorial_findings",
            [],
        )

        if str(
            item.get(
                "statement",
                "",
            )
        ).strip()
    ]


    if not high_level:

        raise Run118ExplainLLMError(
            "Nessun finding deterministico "
            "disponibile per il fallback."
        )


    mode = payload.get(
        "mode"
    )


    # ========================================================
    # SUMMARY
    # ========================================================

    summary_parts = [
        high_level[0]
    ]

    consumed = 1


    # Nel confronto inseriamo anche il cambiamento
    # principale della copertura nel riepilogo iniziale.
    if (
        mode == "comparison"
        and len(
            high_level
        ) > 1
    ):

        summary_parts.append(
            high_level[1]
        )

        consumed = 2


    summary_text = " ".join(
        summary_parts
    )


    # ========================================================
    # MAIN CHANGES
    # ========================================================

    what_changes = (
        high_level[
            consumed:
            consumed + 5
        ]
    )


    # ========================================================
    # IMPORTANT NOTE
    # ========================================================

    severity_source = (
        payload.get(
            "facts",
            {}
        )
        .get(
            "current_run",
            {}
        )
        .get(
            "source",
            {}
        )
        .get(
            "severity_source"
        )
    )

    if mode == "comparison":

        important_note = (
            "Population Health non modifica i codici "
            "di emergenza. Modifica la pesatura "
            "territoriale della domanda utilizzata "
            "dall'ottimizzatore. Le differenze rispetto "
            "alla pianificazione originale descrivono "
            "come cambia la soluzione del modello e "
            "non rappresentano un effetto causale."
        )


    elif (
            severity_source
            == "population_health"
    ):

        important_note = (
            "Population Health non modifica i codici "
            "di emergenza. In questo run modifica "
            "soltanto la pesatura territoriale della "
            "domanda utilizzata dall'ottimizzatore. "
            "Senza un run di riferimento non vengono "
            "dedotte differenze rispetto ad altre "
            "pianificazioni."
        )


    else:

        important_note = (
            "Questa spiegazione descrive esclusivamente "
            "i risultati del run selezionato. "
            "I valori riportati derivano dagli artifact "
            "prodotti dall'ottimizzatore."
        )


    explanation = Run118Explanation(

        title=(
            "Spiegazione della pianificazione 118"
        ),

        summary=
            summary_text,

        what_changes=
            what_changes,

        territorial_notes=
            territorial[:3],

        important_note=
            important_note,
    )


    # Anche il fallback passa attraverso
    # gli stessi controlli del testo LLM.
    _validate_numeric_grounding(
        explanation=explanation,
        payload=payload,
    )

    _validate_semantic_grounding(
        explanation,
        payload=payload,
    )

    _validate_minimum_fact_coverage(
        explanation=explanation,
        payload=payload,
    )


    return explanation


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def explain_118_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:

    # ========================================================
    # CONTRACT VALIDATION
    # ========================================================

    if not isinstance(
        payload,
        Mapping,
    ):

        raise Run118ExplainLLMError(
            "Payload Explain Results 118 non valido."
        )


    if (
        payload.get(
            "contract"
        )
        != "118_llm_grounded_payload_v1"
    ):

        raise Run118ExplainLLMError(
            "Contratto Explain Results 118 "
            "non compatibile."
        )


    mode = payload.get(
        "mode"
    )


    if mode not in {
        "single_run",
        "comparison",
    }:

        raise Run118ExplainLLMError(
            "Modalità Explain Results 118 "
            "non valida."
        )


    high_level_findings = (
        payload.get(
            "high_level_findings",
            [],
        )
    )


    if not high_level_findings:

        raise Run118ExplainLLMError(
            "Nessun finding deterministico "
            "disponibile per la spiegazione."
        )


    # ========================================================
    # MODEL
    # ========================================================

    model = _get_model()

    client = _get_client()


    # Valore di default:
    # verrà usato solo se il modello fallisce.
    fallback_reason = None


    # ========================================================
    # LLM ATTEMPT
    # ========================================================

    try:

        system_prompt = (
            _build_system_prompt()
        )

        user_context = (
            _build_user_context(
                payload
            )
        )


        response = client.chat(

            model=model,

            messages=[
                {
                    "role":
                        "system",

                    "content":
                        system_prompt,
                },

                {
                    "role":
                        "user",

                    "content":
                        user_context,
                },
            ],

            format=(
                Run118Explanation
                .model_json_schema()
            ),

            options={
                "temperature":
                    0,
            },
        )


        content = (
            response
            .message
            .content
        )


        if not content:

            fallback_reason = (
                "empty_llm_response"
            )

        else:

            # =================================================
            # STRUCTURED VALIDATION
            # =================================================

            try:

                parsed = (
                    Run118Explanation
                    .model_validate_json(
                        content
                    )
                )


            except ValidationError:

                fallback_reason = (
                    "invalid_structured_output"
                )

            else:

                # =============================================
                # HARD GROUNDING VALIDATION
                # =============================================

                try:

                    _validate_numeric_grounding(
                        explanation=parsed,
                        payload=payload,
                    )


                except Run118ExplainLLMError:

                    fallback_reason = (
                        "numeric_grounding_failed"
                    )


                else:

                    try:

                        _validate_semantic_grounding(
                            parsed,
                            payload=payload,
                        )


                    except Run118ExplainLLMError:

                        fallback_reason = (
                            "semantic_grounding_failed"
                        )


                    else:

                        try:

                            _validate_minimum_fact_coverage(
                                explanation=parsed,
                                payload=payload,
                            )


                        except Run118ExplainLLMError:

                            fallback_reason = (
                                "fact_coverage_failed"
                            )


                        else:

                            # =====================================
                            # LLM RESPONSE ACCEPTED
                            # =====================================

                            return {

                                "status":
                                    "ok",

                                "contract":
                                    "118_llm_explanation_v2",

                                "grounding_contract":
                                    payload[
                                        "contract"
                                    ],

                                "mode":
                                    mode,

                                "model":
                                    model,

                                "provider":
                                    "ollama_local",

                                "generation": {

                                    "mode":
                                        "llm",

                                    "llm_attempted":
                                        True,

                                    "llm_accepted":
                                        True,

                                    "fallback_used":
                                        False,

                                    "fallback_reason":
                                        None,
                                },

                                "validation": {

                                    "structured_output":
                                        True,

                                    "numeric_grounding":
                                        True,

                                    "semantic_grounding":
                                        True,

                                    "fact_coverage":
                                        True,
                                },

                                "explanation":
                                    parsed.model_dump(),
                            }


    # ========================================================
    # OLLAMA UNAVAILABLE
    # ========================================================

    except RequestError:

        fallback_reason = (
            "llm_unavailable"
        )


    # ========================================================
    # OLLAMA MODEL ERROR
    # ========================================================

    except ResponseError:

        fallback_reason = (
            "llm_generation_error"
        )


    # ========================================================
    # DETERMINISTIC FALLBACK
    # ========================================================

    fallback = (
        _build_deterministic_fallback(
            payload
        )
    )


    return {

        "status":
            "ok",

        "contract":
            "118_llm_explanation_v2",

        "grounding_contract":
            payload[
                "contract"
            ],

        "mode":
            mode,

        # Conserviamo il modello tentato
        # a fini di audit.
        "model":
            model,

        "provider":
            "deterministic_fallback",

        "generation": {

            "mode":
                "deterministic_fallback",

            "llm_attempted":
                True,

            "llm_accepted":
                False,

            "fallback_used":
                True,

            "fallback_reason":
                fallback_reason,
        },

        "validation": {

            "structured_output":
                True,

            "numeric_grounding":
                True,

            "semantic_grounding":
                True,
            "fact_coverage":
                True,
        },

        "explanation":
            fallback.model_dump(),
    }


__all__ = [
    "Run118ExplainLLMUnavailableError",
    "Run118ExplainLLMError",
    "Run118Explanation",
    "explain_118_payload",
]