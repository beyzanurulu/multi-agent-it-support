"""Runs one chat turn (or an approval resume) and yields UI events as it goes."""

import time
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from agent_api.core.auth import Principal
from agent_api.core.config import get_settings
from agent_api.core.metrics import AGENT_LATENCY, FIRST_RESPONSE, GUARDRAIL, REQUESTS
from agent_api.guardrails import limits, pii


def thread_config(principal: Principal, session_id: str) -> dict:
    # Thread ids are scoped to the user, so nobody can resume someone else's conversation.
    return {"configurable": {"thread_id": f"{principal.user_id}:{session_id}"},
            "recursion_limit": get_settings().recursion_limit}


def _serialize_step(step: dict) -> dict:
    return {k: step.get(k) for k in ("id", "intent", "stage", "severity", "note", "outcome",
                                      "kb_sources")}


async def summary(graph, principal: Principal, session_id: str) -> dict:
    snap = await graph.aget_state(thread_config(principal, session_id))
    values = snap.values or {}
    pending = [i.value for task in snap.tasks for i in task.interrupts]
    return {
        "session_id": session_id,
        "plan": [_serialize_step(s) for s in values.get("plan") or []],
        "tickets": values.get("tickets") or [],
        "awaiting": values.get("awaiting"),
        "pending_approval": pending[0] if pending else None,
        "nlu": values.get("nlu"),
    }


async def stream_turn(graph, pool, principal: Principal, session_id: str, *,
                      message: str | None = None, approved: bool | None = None
                      ) -> AsyncIterator[dict]:
    config = thread_config(principal, session_id)
    if message is not None:
        REQUESTS.labels(principal.role).inc()
        if pool is not None:
            ok, reason = await limits.consume_message(pool, principal.user_id)
            if not ok:
                GUARDRAIL.labels("rate_limit").inc()
                yield {"type": "message", "agent": "guardrail", "content": reason}
                yield {"type": "done", **await summary(graph, principal, session_id)}
                return
        masked, found = pii.mask(message)
        if found:
            GUARDRAIL.labels("pii").inc()
            yield {"type": "guardrail", "kind": "pii", "entities": found}
        payload = {"messages": [HumanMessage(content=masked)], "user_id": principal.user_id,
                   "role": principal.role, "department": principal.department}
    else:
        snap = await graph.aget_state(config)
        if not any(t.interrupts for t in snap.tasks):
            yield {"type": "error", "detail": "onay bekleyen işlem yok"}
            return
        payload = Command(resume={"approved": bool(approved), "approver": principal.user_id})

    before = (await graph.aget_state(config)).values.get("tokens", 0)
    started = last = time.perf_counter()
    first = True
    async for mode, chunk in graph.astream(payload, config, stream_mode=["updates", "custom"]):
        if mode == "custom":
            yield chunk
            continue
        for node, delta in chunk.items():
            now = time.perf_counter()
            AGENT_LATENCY.labels(node).observe(now - last)
            last = now
            if node == "__interrupt__":
                value = delta[0].value
                yield {**value, "type": "interrupt", "kind": value["type"]}
                continue
            for msg in (delta or {}).get("messages", []):
                if isinstance(msg, AIMessage):
                    if first:
                        FIRST_RESPONSE.observe(now - started)
                        first = False
                    yield {"type": "message", "agent": msg.name, "content": str(msg.content)}
    state = (await graph.aget_state(config)).values
    if pool is not None:
        await limits.add_tokens(pool, principal.user_id, state.get("tokens", 0) - before)
    yield {"type": "done", **await summary(graph, principal, session_id)}
