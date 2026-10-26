"""Solution agent: hybrid KB search, step-by-step answer that must cite KB sources."""

import re

import structlog
from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore
from langgraph.types import Command
from pydantic import BaseModel, Field

from agent_api.clients import call_tool, emit
from agent_api.core.llm import get_llm, token_usage
from agent_api.core.metrics import GUARDRAIL, TOKENS
from agent_api.graph.common import active, back_to_supervisor, entities, step_text
from agent_api.graph.state import AgentState

log = structlog.get_logger()

HINTS = {"password_reset": "şifre sıfırlama", "account_locked": "hesap kilitlenmesi",
         "vpn_issue": "VPN bağlantı", "email_issue": "Outlook e-posta",
         "software_install": "yazılım kurulumu", "hardware_issue": "donanım arızası",
         "network_issue": "internet ağ bağlantısı", "access_request": "erişim yetki talebi",
         "printer_issue": "yazıcı"}

PROMPT = """Sen kurumsal bir IT destek asistanısın. Kullanıcıya Türkçe, kısa ve numaralı adımlarla
yardım et. SADECE aşağıdaki bilgi tabanı parçalarını kullan; kullandığın her parçanın id'sini
source_ids alanına yaz. Parçalar soruyu karşılamıyorsa steps boş liste olsun.

Bilgi tabanı:
{docs}"""


class SolutionAnswer(BaseModel):
    """Hallucination guard: an answer without at least one KB source is rejected."""

    title: str
    steps: list[str] = Field(min_length=1, max_length=8)
    source_ids: list[str] = Field(min_length=1)


def _steps_from_chunk(content: str) -> list[str]:
    section = content.split("## Çözüm Adımları", 1)[-1].split("##")[0]
    return [re.sub(r"^\d+\.\s*", "", line).strip() for line in section.splitlines()
            if re.match(r"^\d+\.", line.strip())]


async def _llm_answer(question: str, docs: list[dict]) -> tuple[SolutionAnswer | None, int]:
    llm = get_llm()
    if llm is None:
        return None, 0
    context = "\n\n".join(f"[{d['doc_id']}] {d['content']}" for d in docs)
    structured = llm.with_structured_output(SolutionAnswer, include_raw=True)
    out = await structured.ainvoke([("system", PROMPT.format(docs=context)), ("human", question)])
    return out["parsed"], token_usage(out["raw"])


async def solution(state: AgentState, *, store: BaseStore) -> Command:
    step = active(state)
    question = step_text(step)
    docs = await call_tool("solution", state["role"], "search_kb", {
        "query": f"{question} {HINTS.get(step['intent'], '')}",
        "category": step["category"],
        "error_codes": entities(step, "HATA_KODU"),
    })
    if not docs:
        return back_to_supervisor(state, {"stage": "ticket", "kb_sources": []})

    retrieved = {d["doc_id"] for d in docs}
    answer, tokens = None, 0
    try:
        answer, tokens = await _llm_answer(question, docs)
    except Exception as exc:  # noqa: BLE001 - fall back to the retrieved article
        log.warning("solution.llm_failed", error=str(exc))
    if answer and not set(answer.source_ids) <= retrieved:
        GUARDRAIL.labels("hallucinated_source").inc()
        emit({"type": "guardrail", "kind": "hallucinated_source", "sources": answer.source_ids})
        answer = None
    if answer is None:
        top = docs[0]
        steps = _steps_from_chunk(top["content"])
        if not steps:
            return back_to_supervisor(state, {"stage": "ticket", "kb_sources": []})
        answer = SolutionAnswer(title=top["title"], steps=steps, source_ids=[top["doc_id"]])
    TOKENS.labels("solution").inc(tokens)

    body = "\n".join(f"{i}. {s}" for i, s in enumerate(answer.steps, 1))
    text = (f"**{answer.title}**\n{body}\n\n_Kaynak: {', '.join(answer.source_ids)}_\n\n"
            "Bu adımlar işe yaradı mı?")
    return back_to_supervisor(
        state, {"stage": "feedback", "kb_sources": answer.source_ids},
        awaiting={"kind": "feedback", "step": step["id"]},
        tokens=state.get("tokens", 0) + tokens,
        messages=[AIMessage(content=text, name="solution")])
