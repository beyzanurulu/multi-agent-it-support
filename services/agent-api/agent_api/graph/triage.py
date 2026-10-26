"""Triage agent: urgency, category, service status, missing information."""

import re

from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore
from langgraph.types import Command

from agent_api.clients import call_tool, emit
from agent_api.graph.common import active, back_to_supervisor, entities, step_text
from agent_api.graph.state import AgentState

BASE_SEVERITY = {"password_reset": "medium", "account_locked": "high", "vpn_issue": "medium",
                 "email_issue": "medium", "software_install": "low", "hardware_issue": "medium",
                 "network_issue": "medium", "access_request": "low", "printer_issue": "low"}
SERVICE = {"vpn_issue": "vpn", "email_issue": "email", "network_issue": "wifi",
           "account_locked": "sso", "password_reset": "sso", "printer_issue": "printserver"}
CRITICAL = re.compile(r"herkes|tüm (ofis|şirket|departman)|kimse çalışamıyor|üretim durdu|"
                      r"production", re.IGNORECASE)
HIGH = re.compile(r"acil|hemen|çalışamıyorum|toplantım|sunumum|müşteri bekliyor", re.IGNORECASE)
ORDER = ["low", "medium", "high", "critical"]
# intent -> (entity labels that already answer the question, question)
MISSING = {
    "hardware_issue": (("CIHAZ",), "Hangi cihazda sorun yaşıyorsunuz (laptop, monitör, klavye...)?"),
    "access_request": (("YAZILIM", "DEPARTMAN"), "Hangi sisteme veya klasöre erişim istiyorsunuz?"),
    "software_install": (("YAZILIM",), "Hangi yazılımın kurulmasını istiyorsunuz?"),
}


def _raise(sev: str, to: str) -> str:
    return max(sev, to, key=ORDER.index)


async def triage(state: AgentState, *, store: BaseStore) -> Command:
    step = active(state)
    role = state["role"]
    text = step_text(step)

    if step["intent"] in MISSING and not step.get("asked") and not step.get("extra"):
        labels, question = MISSING[step["intent"]]
        if not any(entities(step, label) for label in labels):
            return back_to_supervisor(
                state, {"asked": True, "stage": "info"},
                awaiting={"kind": "info", "step": step["id"]},
                messages=[AIMessage(content=question, name="triage")])

    severity = BASE_SEVERITY.get(step["intent"], "low")
    if CRITICAL.search(text):
        severity = "critical"
    elif HIGH.search(text):
        severity = _raise(severity, "high")

    user = await call_tool("triage", role, "get_user_info", {"user_id": state["user_id"]})
    if user.get("vip"):
        severity = _raise(severity, "high")

    notes, stage = [], "solution"
    if service := SERVICE.get(step["intent"]):
        status = await call_tool("triage", role, "check_system_status", {"service_name": service})
        if status["status"] in ("degraded", "outage"):
            severity = _raise(severity, "high")
            notes.append(f"{service} servisi şu an '{status['status']}'")
            stage = "ticket"  # nothing the user can fix; go straight to a ticket

    past = await store.asearch(("users", state["user_id"], "issues"), limit=20)
    similar = [p.value for p in past if p.value.get("intent") == step["intent"]]
    if similar:
        notes.append(f"bu kullanıcı bu sorunu daha önce {len(similar)} kez yaşadı")

    note = "; ".join(notes)
    emit({"type": "triage", "step": step["id"], "severity": severity, "note": note})
    messages = []
    if stage == "ticket":
        messages.append(AIMessage(content=f"{notes[0].capitalize()}. Sizin için destek talebi "
                                          "hazırlıyorum.", name="triage"))
    return back_to_supervisor(state, {"severity": severity, "stage": stage, "note": note},
                              messages=messages)
