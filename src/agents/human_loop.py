"""Human-in-the-loop: an operator approves critical escalations.

The node pauses the graph with `interrupt()`; the checkpointer persists the
state until the API/CLI resumes it with `Command(resume={"approved": ...})`.
"""

from langchain_core.messages import AIMessage
from langgraph.types import interrupt

from src.agents.state import AgentState
from src.agents.triage import last_user_text


def human_approval_node(state: AgentState) -> dict:
    decision = interrupt({
        "type": "escalation_approval",
        "question": "Kritik öncelikli talep L2'ye eskale edilsin mi?",
        "user_id": state.get("user_id"),
        "intent": state.get("intent"),
        "severity": state.get("severity"),
        "user_message": last_user_text(state),
    })
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    note = decision.get("note", "") if isinstance(decision, dict) else ""

    update: dict = {
        "current_agent": "human_approval",
        "approval_status": "approved" if approved else "rejected",
        "approval_note": note,
    }
    if not approved:
        # Operator judged it non-critical: open a normal high-priority ticket instead.
        update.update(severity="high", human_requested=True)
    update["messages"] = [AIMessage(
        content="Talebiniz operatör tarafından kritik olarak onaylandı."
        if approved else "Talebiniz operatör incelemesinden sonra yüksek öncelikle işlenecek.",
        name="human_approval",
    )]
    return update
