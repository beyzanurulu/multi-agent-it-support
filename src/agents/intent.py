"""Intent classification: few-shot LLM with a keyword fallback.

The keyword classifier is deterministic and always available (tests, no API
key, LLM failure). The LLM path is used when OPENAI_API_KEY is configured.
"""

import re

import structlog
from pydantic import BaseModel, Field

from src.agents.state import Severity
from src.core.config import get_settings

log = structlog.get_logger()

# intent -> (category, default severity, keywords)
INTENTS: dict[str, tuple[str, Severity, tuple[str, ...]]] = {
    "password_reset": (
        "account", "medium",
        ("password", "şifre", "parola", "locked out", "hesap kilit", "reset", "sıfırla"),
    ),
    "software_install": (
        "software", "low",
        ("install", "kurulum", "yükle", "license", "lisans", "software", "yazılım", "update"),
    ),
    "network": (
        "network", "medium",
        ("vpn", "wifi", "wi-fi", "internet", "network", "ağ", "bağlantı", "connection", "dns"),
    ),
    "hardware": (
        "hardware", "medium",
        ("laptop", "printer", "yazıcı", "monitor", "ekran", "keyboard", "klavye", "mouse"),
    ),
    "email": (
        "email", "medium",
        ("email", "e-posta", "outlook", "mailbox", "mail"),
    ),
    "access_request": (
        "access", "low",
        ("access", "erişim", "permission", "yetki", "izin"),
    ),
    "security_incident": (
        "security", "critical",
        ("phishing", "virus", "virüs", "malware", "hack", "ransomware", "breach", "şüpheli"),
    ),
}
FALLBACK_INTENT = "other"

CRITICAL_MARKERS = ("production down", "prod down", "tüm şirket", "everyone", "herkes", "outage")
HIGH_MARKERS = ("urgent", "acil", "asap", "hemen", "cannot work", "çalışamıyorum")
HUMAN_MARKERS = ("human", "insan", "operator", "operatör", "agent ile görüş", "talk to someone")


class IntentResult(BaseModel):
    intent: str = Field(description=f"One of: {', '.join([*INTENTS, FALLBACK_INTENT])}")
    category: str
    severity: Severity
    human_requested: bool = False


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(w)}", text) for w in words)


def classify_keywords(text: str) -> IntentResult:
    lowered = text.lower()
    scores = {
        name: sum(1 for w in kws if _contains(lowered, (w,)))
        for name, (_, _, kws) in INTENTS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        intent, category, severity = FALLBACK_INTENT, "general", "low"
    else:
        intent = best
        category, severity, _ = INTENTS[best]

    if _contains(lowered, CRITICAL_MARKERS):
        severity = "critical"
    elif _contains(lowered, HIGH_MARKERS) and severity in ("low", "medium"):
        severity = "high"

    return IntentResult(
        intent=intent,
        category=category,
        severity=severity,
        human_requested=_contains(lowered, HUMAN_MARKERS),
    )


FEW_SHOT_PROMPT = """You are the triage classifier of an enterprise IT helpdesk.
Classify the user's message. Valid intents: {intents}.
Severity: low | medium | high | critical (critical = security incident or wide outage).

Examples:
- "Şifremi unuttum, hesabım kilitlendi" -> password_reset, account, medium
- "Need Photoshop installed on my laptop" -> software_install, software, low
- "VPN bağlanmıyor, evden çalışamıyorum, acil" -> network, network, high
- "I clicked a phishing link and entered my password" -> security_incident, security, critical
- "Printer on 3rd floor jams constantly" -> hardware, hardware, medium
"""


def classify_llm(text: str) -> IntentResult:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)
    structured = llm.with_structured_output(IntentResult)
    prompt = FEW_SHOT_PROMPT.format(intents=", ".join([*INTENTS, FALLBACK_INTENT]))
    return structured.invoke([("system", prompt), ("human", text)])


def classify(text: str) -> IntentResult:
    if get_settings().llm_enabled:
        try:
            result = classify_llm(text)
            if result.intent in INTENTS or result.intent == FALLBACK_INTENT:
                return result
            log.warning("intent.llm_invalid", intent=result.intent)
        except Exception as exc:  # noqa: BLE001 - fall back on any provider error
            log.warning("intent.llm_failed", error=str(exc))
    return classify_keywords(text)
