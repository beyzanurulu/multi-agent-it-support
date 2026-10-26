"""Shared agent state (shared memory between agents; persisted by the checkpointer)."""

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

Role = Literal["employee", "it_specialist", "manager"]
Stage = Literal["triage", "solution", "feedback", "ticket", "info", "done"]


class PlanStep(TypedDict, total=False):
    id: int
    intent: str
    agent: str          # first agent responsible for the step
    stage: Stage
    severity: str
    category: str
    text: str           # user text the step was planned from (PII-masked)
    entities: list[dict]  # NER output of that text
    note: str           # planner/triage reasoning shown in the UI
    asked: bool         # triage already asked for missing info
    extra: str          # user's answer to the missing-info question
    kb_sources: list[str]
    outcome: str        # resolved | ticket | skipped | refused | answered


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_id: str
    role: Role
    department: str | None

    turn_text: str                  # PII-masked text of the current user turn
    nlu: dict                       # {"intents": [...], "entities": [...], "backend": ...}
    plan: list[PlanStep]
    active_step: int | None
    awaiting: dict | None           # {"kind": "feedback" | "info", "step": id}

    tickets: Annotated[list[dict], operator.add]
    analytics: dict | None
    step_count: int
    tokens: int
