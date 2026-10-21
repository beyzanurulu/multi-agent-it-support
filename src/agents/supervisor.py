"""Supervisor: decides which specialised agent runs next."""

import re

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.intent import FALLBACK_INTENT
from src.agents.state import AgentName, AgentState
from src.guardrails.loop_guard import limit_reached

NEGATIVE_FEEDBACK = (
    "olmadı", "çözülmedi", "çözemedi", "işe yaramadı", "hâlâ", "hala", "devam ediyor",
    "değil", "yok", "not", "still", "didn't", "doesn't", "no",
)
POSITIVE_FEEDBACK = (
    "çözüldü", "oldu", "teşekkür", "işe yaradı", "düzeldi", "evet",
    "solved", "fixed", "works", "thanks", "yes",
)


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) for w in words)


def solution_feedback(state: AgentState) -> bool | None:
    """Read the user's reply to a proposed solution, if there is one."""
    messages = state.get("messages", [])
    if not state.get("proposed_solution") or not messages:
        return None
    last = messages[-1]
    if not isinstance(last, HumanMessage):
        return None
    text = str(last.content).lower()
    if _has_word(text, NEGATIVE_FEEDBACK):
        return False
    return any(word in text for word in POSITIVE_FEEDBACK)


def route(state: AgentState) -> AgentName:
    if not state.get("intent"):
        return "triage"
    if state.get("ticket_id"):
        return "end"
    if state.get("severity") == "critical" and "approval_status" not in state:
        return "human_approval"
    # Critical issues, unclassifiable issues and explicit human requests skip self-service.
    if (
        state.get("severity") == "critical"
        or state.get("human_requested")
        or state.get("intent") == FALLBACK_INTENT
    ):
        return "ticket"
    if not state.get("proposed_solution"):
        return "solution"
    if "solution_accepted" not in state:
        return "end"  # wait for the user's feedback on the proposal
    return "end" if state["solution_accepted"] else "ticket"


def supervisor_node(state: AgentState) -> dict:
    update: dict = {
        "iteration_count": state.get("iteration_count", 0) + 1,
        "current_agent": "supervisor",
    }
    if limit_reached(state):
        update["next_agent"] = "end"
        update["messages"] = [AIMessage(
            content="Talebinizi otomatik olarak sonuçlandıramadım; "
            "bir destek uzmanı sizinle iletişime geçecek.",
            name="supervisor",
        )]
        return update

    feedback = solution_feedback(state)
    if feedback is not None:
        update["solution_accepted"] = feedback
    update["next_agent"] = route({**state, **update})
    return update
