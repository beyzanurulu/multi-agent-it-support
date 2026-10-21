"""Shared LangGraph state for all agents."""

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

Severity = Literal["low", "medium", "high", "critical"]
AgentName = Literal["supervisor", "triage", "solution", "ticket", "end"]


class AgentState(TypedDict, total=False):
    # Conversation
    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str

    # Triage
    intent: str
    severity: Severity
    category: str

    # Solution
    kb_results: list[dict]
    proposed_solution: str
    solution_accepted: bool

    # Ticket
    ticket_id: str | None
    ticket_status: str
    escalated: bool

    # Control
    current_agent: AgentName
    next_agent: AgentName
    iteration_count: int
    human_requested: bool
