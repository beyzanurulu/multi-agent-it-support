"""Triage agent: classifies the issue and collects metadata."""

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.intent import classify
from src.agents.state import AgentState


def last_user_text(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


def triage_node(state: AgentState) -> dict:
    result = classify(last_user_text(state))
    return {
        "current_agent": "triage",
        "intent": result.intent,
        "category": result.category,
        "severity": result.severity,
        "human_requested": result.human_requested,
        "messages": [AIMessage(
            content=f"Sorun sınıflandırıldı: {result.intent} "
            f"(kategori: {result.category}, öncelik: {result.severity}).",
            name="triage",
        )],
    }
