"""Runs graph turns for the API and turns state into response payloads."""

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

SUMMARY_FIELDS = (
    "intent", "severity", "category", "proposed_solution", "solution_accepted",
    "ticket_id", "ticket_status", "escalated", "approval_status", "current_agent",
    "iteration_count",
)


def config_for(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def turn_input(message: str, user_id: str) -> dict:
    return {"messages": [HumanMessage(content=message)], "user_id": user_id, "iteration_count": 0}


def resume_input(approved: bool, note: str = "") -> Command:
    return Command(resume={"approved": approved, "note": note})


def serialize_message(msg) -> dict:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    return {"role": role, "agent": getattr(msg, "name", None), "content": str(msg.content)}


async def snapshot(graph, session_id: str) -> dict:
    state = await graph.aget_state(config_for(session_id))
    values = state.values or {}
    pending = [i.value for task in state.tasks for i in task.interrupts]
    return {
        "session_id": session_id,
        "state": {k: values.get(k) for k in SUMMARY_FIELDS},
        "messages": [serialize_message(m) for m in values.get("messages", [])],
        "pending_approval": pending[0] if pending else None,
    }


async def run_turn(graph, session_id: str, payload) -> dict:
    before = len((await graph.aget_state(config_for(session_id))).values.get("messages", []))
    await graph.ainvoke(payload, config_for(session_id))
    snap = await snapshot(graph, session_id)
    snap["new_messages"] = [m for m in snap["messages"][before:] if m["role"] == "assistant"]
    return snap


async def stream_turn(graph, session_id: str, payload) -> AsyncIterator[dict]:
    """Yield one event per agent step, then a final snapshot event."""
    async for update in graph.astream(payload, config_for(session_id), stream_mode="updates"):
        for node, delta in update.items():
            if node == "__interrupt__":
                yield {"type": "interrupt", "payload": delta[0].value}
                continue
            delta = delta or {}
            yield {
                "type": "agent_step",
                "agent": node,
                "next_agent": delta.get("next_agent"),
                "messages": [
                    serialize_message(m) for m in delta.get("messages", [])
                    if isinstance(m, AIMessage)
                ],
            }
    yield {"type": "done", **(await snapshot(graph, session_id))}
