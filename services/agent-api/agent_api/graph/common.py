from langgraph.types import Command

from agent_api.graph.planner import update_step
from agent_api.graph.state import AgentState, PlanStep


def active(state: AgentState) -> PlanStep:
    return next(s for s in state["plan"] if s["id"] == state["active_step"])


def back_to_supervisor(state: AgentState, step_changes: dict | None = None, **update) -> Command:
    """Message passing: every agent hands control back to the supervisor via Command."""
    if step_changes:
        update["plan"] = update_step(state["plan"], state["active_step"], **step_changes)
    return Command(goto="supervisor", update=update)


def entities(step: PlanStep, label: str) -> list[str]:
    return [e["text"] for e in step.get("entities", []) if e["label"] == label]


def step_text(step: PlanStep) -> str:
    return f"{step.get('text', '')} {step.get('extra', '')}".strip()
