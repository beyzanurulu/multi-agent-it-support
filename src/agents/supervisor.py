"""Supervisor: decides which specialised agent runs next."""

from langchain_core.messages import AIMessage, HumanMessage

from src.agents.state import AgentName, AgentState
from src.guardrails.loop_guard import limit_reached

POSITIVE_FEEDBACK = ("çözüldü", "oldu", "teşekkür", "işe yaradı", "solved", "fixed", "works", "thanks")


def solution_feedback(state: AgentState) -> bool | None:
    """Read the user's reply to a proposed solution, if there is one."""
    messages = state.get("messages", [])
    if not state.get("proposed_solution") or not messages:
        return None
    last = messages[-1]
    if not isinstance(last, HumanMessage):
        return None
    text = str(last.content).lower()
    return any(word in text for word in POSITIVE_FEEDBACK)


def route(state: AgentState) -> AgentName:
    if not state.get("intent"):
        return "triage"
    if state.get("ticket_id"):
        return "end"
    # Critical issues and explicit human requests skip self-service.
    if state.get("severity") == "critical" or state.get("human_requested"):
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
