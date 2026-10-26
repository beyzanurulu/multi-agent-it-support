"""Entry guard, NLU and the planner/supervisor that hands work to agents via Command."""

import time
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END
from langgraph.store.base import BaseStore
from langgraph.types import Command

from agent_api.clients import analyze_text, emit
from agent_api.core.metrics import AGENT_LATENCY, GUARDRAIL
from agent_api.graph.feedback import classify_feedback
from agent_api.graph.planner import build_plan, describe, next_step, update_step
from agent_api.graph.state import AgentState
from agent_api.guardrails import injection
from agent_api.guardrails.limits import step_limit_reached

OTHER_REPLY = ("Bu mesajı bir IT talebi olarak anlayamadım. Yaşadığınız sorunu biraz daha "
               "açar mısınız? (ör. hangi uygulama/cihaz, aldığınız hata mesajı)")


def last_user_text(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


async def guard_in(state: AgentState) -> Command:
    text = last_user_text(state)
    result = injection.check(text)
    if result.blocked:
        GUARDRAIL.labels("prompt_injection").inc()
        emit({"type": "guardrail", "kind": "prompt_injection", "score": result.score})
        return Command(goto=END, update={"messages": [AIMessage(
            content="Bu isteği güvenlik politikası gereği işleyemiyorum. IT ile ilgili bir "
                    "sorununuz varsa onu yazabilirsiniz.", name="guardrail")]})
    return Command(goto="nlu", update={"turn_text": text, "step_count": 0})


async def nlu_node(state: AgentState) -> dict:
    started = time.perf_counter()
    result = await analyze_text(state["turn_text"])
    AGENT_LATENCY.labels("nlu").observe(time.perf_counter() - started)
    emit({"type": "nlu", **result})
    return {"nlu": result}


def _start_new_plan(state: AgentState) -> dict:
    last_id = max((s["id"] for s in state.get("plan") or []), default=0)
    plan = build_plan(state["nlu"]["intents"], start_id=last_id + 1, text=state["turn_text"],
                      entities=state["nlu"].get("entities", []))
    emit({"type": "plan", "steps": plan})
    return {"plan": plan, "awaiting": None}


def _absorb_turn(state: AgentState) -> dict:
    """Decide what the new user message means given what we were waiting for."""
    awaiting = state.get("awaiting")
    plan = state.get("plan") or []
    if not awaiting:
        return _start_new_plan(state)

    step_id = awaiting["step"]
    if awaiting["kind"] == "info":
        return {"plan": update_step(plan, step_id, stage="triage", extra=state["turn_text"]),
                "awaiting": None}

    solved = classify_feedback(state["turn_text"])
    real_intents = [i for i in state["nlu"]["intents"] if i["label"] != "other"]
    if solved is None and real_intents:
        # Not an answer to the proposal but a new problem: close the old step, plan anew.
        plan = update_step(plan, step_id, stage="done", outcome="unanswered")
        new = build_plan(state["nlu"]["intents"], start_id=max(s["id"] for s in plan) + 1,
                         text=state["turn_text"], entities=state["nlu"].get("entities", []))
        emit({"type": "plan", "steps": new})
        return {"plan": plan + new, "awaiting": None}
    if solved:
        emit({"type": "plan_revision", "step": step_id, "change": "çözüldü, sonraki adıma geç"})
        return {"plan": update_step(plan, step_id, stage="done", outcome="resolved"),
                "awaiting": None}
    emit({"type": "plan_revision", "step": step_id, "change": "çözüm işe yaramadı → ticket"})
    return {"plan": update_step(plan, step_id, stage="ticket"), "awaiting": None}


async def _remember_resolved(store: BaseStore, state: AgentState, before: list, after: list):
    was = {s["id"]: s.get("outcome") for s in before}
    for step in after:
        if step.get("outcome") == "resolved" and was.get(step["id"]) != "resolved":
            await store.aput(("users", state["user_id"], "issues"), str(uuid.uuid4()),
                             {"intent": step["intent"], "outcome": "resolved",
                              "sources": step.get("kb_sources", [])})


async def supervisor(state: AgentState, *, store: BaseStore) -> Command:
    update: dict = {"step_count": state.get("step_count", 0) + 1}
    if state.get("step_count", 0) == 0 and state.get("turn_text"):
        update |= _absorb_turn(state)
        await _remember_resolved(store, state, state.get("plan") or [], update.get("plan") or [])
    merged = {**state, **update}

    if step_limit_reached(state.get("step_count", 0)):
        GUARDRAIL.labels("max_steps").inc()
        open_steps = [s["intent"] for s in merged.get("plan", []) if s["stage"] != "done"]
        update["messages"] = [AIMessage(
            content="İşlem adım sınırına ulaştı. Özet: " +
                    (f"tamamlanmayan adımlar: {', '.join(open_steps)}. " if open_steps else "") +
                    "Gerekirse bir destek uzmanı sizinle iletişime geçecek.", name="supervisor")]
        return Command(goto=END, update=update)

    if merged.get("awaiting"):
        return Command(goto=END, update=update)

    step = next_step(merged.get("plan") or [])
    if step is None:
        return Command(goto=END, update=update)

    if step["intent"] == "other":
        update["plan"] = update_step(merged["plan"], step["id"], stage="done", outcome="answered")
        update["messages"] = [AIMessage(content=OTHER_REPLY, name="supervisor")]
        return Command(goto="supervisor", update=update)

    agent = {"triage": "triage", "solution": "solution", "ticket": "ticket"}.get(step["stage"])
    if step["intent"] == "report_request":
        agent = "analytics"
    emit({"type": "route", "step": step["id"], "intent": step["intent"], "agent": agent,
          "plan": describe(merged["plan"])})
    update["active_step"] = step["id"]
    return Command(goto=agent, update=update)
