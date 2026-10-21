"""Ticket agent.

Week 1 placeholder: generates a local ticket id. Week 2 swaps this for the
FastMCP `create_ticket` / `escalate_ticket` tools backed by the mock CRM.
"""

import uuid

from langchain_core.messages import AIMessage

from src.agents.state import AgentState


def ticket_node(state: AgentState) -> dict:
    ticket_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
    escalated = state.get("severity") == "critical"
    status = "escalated" if escalated else "open"
    return {
        "current_agent": "ticket",
        "ticket_id": ticket_id,
        "ticket_status": status,
        "escalated": escalated,
        "messages": [AIMessage(
            content=f"Destek talebiniz oluşturuldu: {ticket_id} "
            f"(öncelik: {state.get('severity', 'low')}, durum: {status}).",
            name="ticket",
        )],
    }
