"""Solution agent: RAG over the IT knowledge base via FastMCP tools."""

import structlog
from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.agents.triage import last_user_text
from src.core.config import get_settings
from src.guardrails.output_validator import validate_solution
from src.tools.crm import SYSTEM_STATUS
from src.tools.server import call_tool

log = structlog.get_logger()

# Domain phrases appended to the user's message to sharpen retrieval.
QUERY_HINTS = {
    "password_reset": "şifre sıfırlama hesap kilitlenmesi",
    "software_install": "yazılım kurulumu software center",
    "network": "ağ bağlantısı vpn internet",
    "hardware": "donanım cihaz",
    "email": "outlook e-posta",
    "access_request": "erişim talebi yetki",
    "security_incident": "güvenlik ihlali",
}

ANSWER_PROMPT = """You are an enterprise IT support assistant. Answer in the user's language.
Use ONLY the knowledge base articles below. Give short, numbered steps.
If the articles do not cover the issue, reply exactly: NO_ANSWER

Articles:
{articles}"""


def _format_answer(doc: dict) -> str:
    steps = doc["content"].split("## Çözüm Adımları", 1)[-1].split("##")[0].strip()
    return f"**{doc['title']}**\n{steps}\n\nBu adımlar sorununuzu çözdü mü?"


def _llm_answer(question: str, docs: list[dict]) -> str | None:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)
    articles = "\n\n".join(f"[{d['id']}]\n{d['content']}" for d in docs)
    reply = llm.invoke([("system", ANSWER_PROMPT.format(articles=articles)), ("human", question)])
    text = str(reply.content).strip()
    return None if "NO_ANSWER" in text else f"{text}\n\nBu adımlar sorununuzu çözdü mü?"


async def _service_outage(text: str) -> dict | None:
    lowered = text.lower()
    for service in SYSTEM_STATUS:
        if service in lowered:
            status = await call_tool("check_system_status", {"service_name": service})
            if status["status"] != "operational":
                return status
    return None


async def solution_node(state: AgentState) -> dict:
    question = last_user_text(state)
    update: dict = {"current_agent": "solution"}

    outage = await _service_outage(question)
    if outage:
        # A known service problem cannot be fixed by the user; hand over to ticketing.
        update.update(kb_results=[], proposed_solution="", human_requested=True)
        update["messages"] = [AIMessage(
            content=f"'{outage['service']}' servisinde şu an sorun var "
            f"(durum: {outage['status']}). Sizin için talep oluşturuyorum.",
            name="solution",
        )]
        return update

    query = f"{question} {QUERY_HINTS.get(state.get('intent', ''), '')}".strip()
    results = await call_tool(
        "search_knowledge_base", {"query": query, "category": state.get("category")}
    )
    relevant = [r for r in results if r["score"] >= get_settings().kb_min_score]
    update["kb_results"] = relevant

    answer = None
    if relevant:
        answer = _format_answer(relevant[0])
        if get_settings().llm_enabled:
            try:
                answer = _llm_answer(question, relevant)
            except Exception as exc:  # noqa: BLE001 - keep the retrieval answer
                log.warning("solution.llm_failed", error=str(exc))

    if answer:
        valid, reason = validate_solution(answer)
        if not valid:
            log.warning("solution.guardrail_blocked", reason=reason)
            answer = None

    if not answer:
        update.update(proposed_solution="", human_requested=True)
        return update

    update["proposed_solution"] = answer
    update["messages"] = [AIMessage(content=answer, name="solution")]
    return update
