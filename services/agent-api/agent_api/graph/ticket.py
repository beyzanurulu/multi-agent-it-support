"""Ticket agent: drafts a ticket, waits for human approval (interrupt), then writes it."""

import uuid

from langchain_core.messages import AIMessage
from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt

from agent_api.clients import call_tool
from agent_api.graph.common import active, back_to_supervisor, entities
from agent_api.graph.state import AgentState

TITLES = {"password_reset": "Şifre sıfırlama", "account_locked": "Hesap kilitlenmesi",
          "vpn_issue": "VPN bağlantı sorunu", "email_issue": "E-posta sorunu",
          "software_install": "Yazılım kurulum talebi", "hardware_issue": "Donanım arızası",
          "network_issue": "Ağ bağlantı sorunu", "access_request": "Erişim talebi",
          "printer_issue": "Yazıcı sorunu"}
STATUS_TR = {"open": "açık", "in_progress": "işlemde", "escalated": "eskale edildi",
             "resolved": "çözüldü", "closed": "kapandı"}


def _draft(state: AgentState, step: dict) -> dict:
    details = [f"{e['label']}={e['text']}" for e in step.get("entities", [])]
    title = TITLES.get(step["intent"], "IT talebi")
    siblings = [s for s in state["plan"] if s.get("text") == step.get("text")]
    software = entities(step, "YAZILIM")
    if len(siblings) == 1 and len(software) == 1:  # in multi-intent text it may be the other issue
        title += f" ({software[0]})"
    description = step.get("text") or state["turn_text"]
    if step.get("extra"):
        description += f"\nEk bilgi: {step['extra']}"
    if step.get("kb_sources"):
        description += f"\nDenenen KB çözümü işe yaramadı: {', '.join(step['kb_sources'])}"
    if step.get("note"):
        description += f"\nTriage notu: {step['note']}"
    if details:
        description += f"\nNER: {', '.join(details)}"
    return {"user_id": state["user_id"], "title": title, "description": description,
            "intent": step["intent"], "category": step["category"],
            "severity": step.get("severity", "medium")}


async def _ticket_status(state: AgentState) -> Command:
    user = await call_tool("ticket", state["role"], "get_user_info", {"user_id": state["user_id"]})
    tickets = user.get("tickets", [])[:5]
    if not tickets:
        text = "Kayıtlı bir destek talebiniz bulunmuyor."
    else:
        rows = "\n".join(f"| {t['ticket_no']} | {t['title']} | {STATUS_TR.get(t['status'], t['status'])}"
                         f" | {t['severity']} |" for t in tickets)
        text = ("Son talepleriniz:\n\n| No | Başlık | Durum | Öncelik |\n|---|---|---|---|\n"
                + rows)
    return back_to_supervisor(state, {"stage": "done", "outcome": "answered"},
                              messages=[AIMessage(content=text, name="ticket")])


async def ticket(state: AgentState, *, store: BaseStore) -> Command:
    step = active(state)
    if step["intent"] == "ticket_status":
        return await _ticket_status(state)

    draft = _draft(state, step)
    decision = interrupt({
        "type": "ticket_approval",
        "step": step["id"],
        "question": "Aşağıdaki destek talebini oluşturayım mı?",
        "draft": draft,
        "escalate": draft["severity"] == "critical",
    })
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    approver = (decision.get("approver") if isinstance(decision, dict) else None) or state["user_id"]
    if not approved:
        return back_to_supervisor(
            state, {"stage": "done", "outcome": "skipped"},
            messages=[AIMessage(content="Tamam, talep oluşturmadım.", name="ticket")])

    role = state["role"]
    created = await call_tool("ticket", role, "create_ticket", {**draft, "approved_by": approver})
    if draft["severity"] == "critical":
        created = await call_tool("ticket", role, "escalate_ticket", {
            "ticket_no": created["ticket_no"], "reason": "kritik öncelik", "approved_by": approver})
    text = (f"Destek talebiniz oluşturuldu: **{created['ticket_no']}** — öncelik "
            f"{created['severity']}, ekip {created['assigned_team']}, durum "
            f"{STATUS_TR.get(created['status'], created['status'])}.")
    await call_tool("ticket", role, "notify", {"user_id": state["user_id"], "message": text,
                                               "channel": "email"})
    await store.aput(("users", state["user_id"], "issues"), str(uuid.uuid4()),
                     {"intent": step["intent"], "outcome": "ticket",
                      "ticket_no": created["ticket_no"]})
    return back_to_supervisor(state, {"stage": "done", "outcome": "ticket"},
                              tickets=[created], messages=[AIMessage(content=text, name="ticket")])
