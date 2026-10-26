"""PII masking with Presidio pattern recognizers (Turkish TC no, phone, e-mail, IBAN).

Only pattern recognizers are used, so no spaCy language model is needed. Masking
runs on user input before it reaches an LLM, a log line or a ticket description.
"""

from functools import lru_cache

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


class TcKimlikRecognizer(PatternRecognizer):
    def __init__(self) -> None:
        super().__init__(supported_entity="TC_KIMLIK", supported_language="tr",
                         patterns=[Pattern("tc", r"\b[1-9]\d{10}\b", 0.5)])

    def validate_result(self, pattern_text: str) -> bool:
        d = [int(c) for c in pattern_text]
        check10 = ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10
        return d[9] == check10 and d[10] == sum(d[:10]) % 10


RECOGNIZERS = [
    TcKimlikRecognizer(),
    PatternRecognizer(supported_entity="TELEFON", supported_language="tr", patterns=[
        Pattern("tr_mobile", r"(?<!\d)(?:\+90[\s-]?|0)?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}"
                             r"(?!\d)", 0.7)]),
    PatternRecognizer(supported_entity="EPOSTA", supported_language="tr", patterns=[
        Pattern("email", r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", 0.9)]),
    PatternRecognizer(supported_entity="IBAN", supported_language="tr", patterns=[
        Pattern("iban", r"\bTR\d{2}[\s]?(?:\d{4}[\s]?){5}\d{2}\b", 0.9)]),
]


@lru_cache
def _anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def detect(text: str) -> list[RecognizerResult]:
    results: list[RecognizerResult] = []
    for rec in RECOGNIZERS:
        results.extend(rec.analyze(text, entities=rec.supported_entities, nlp_artifacts=None) or [])
    return [r for r in results if r.score >= 0.5]


def mask(text: str) -> tuple[str, list[str]]:
    """Return the masked text and the entity types that were found."""
    found = detect(text)
    if not found:
        return text, []
    operators = {r.entity_type: OperatorConfig("replace", {"new_value": f"<{r.entity_type}>"})
                 for r in found}
    masked = _anonymizer().anonymize(text=text, analyzer_results=found, operators=operators)
    return masked.text, sorted({r.entity_type for r in found})
