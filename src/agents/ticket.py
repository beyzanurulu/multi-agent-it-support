"""Ticket agent: creates, escalates and notifies via FastMCP tools."""

from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.agents.triage import last_user_text
from src.guardrails.output_validator import validate_ticket
from src.tools.server import call_tool

SEVERITY_ORDER = ["low", "medium", "high", "critical"]

TITLES = {
    "password_reset": "Şifre / hesap sorunu",
    "software_install": "Yazılım kurulum talebi",
    "network": "Ağ bağlantı sorunu",
    "hardware": "Donanım arızası",
    "email": "E-posta sorunu",
    "access_request": "Erişim talebi",
    "security_incident": "Güvenlik olayı",
}


def _bump(severity: str) -> str:
    idx = SEVERITY_ORDER.index(severity)
    return SEVERITY_ORDER[min(idx + 1, len(SEVERITY_ORDER) - 2)] if idx < 2 else severity


async def ticket_node(state: AgentState) -> dict:
    user_id = state.get("user_id") or "anonymous"
    severity = state.get("severity", "low")

    user = await call_tool("get_user_info", {"user_id": user_id})
    if user.get("vip"):
        severity = _bump(severity)

    description = last_user_text(state)
    if state.get("proposed_solution") and state.get("solution_accepted") is False:
        description += "\n\n(Önerilen self-servis çözümü sorunu gidermedi.)"

    payload = validate_ticket({
        "user_id": user_id,
        "title": TITLES.get(state.get("intent", ""), "Genel IT talebi"),
        "description": description[:4000],
        "severity": severity,
        "category": state.get("category", "general"),
    })
    ticket = await call_tool("create_ticket", payload)

    # Reaching here with "critical" means an operator approved the escalation.
    if severity == "critical":
        ticket = await call_tool(
            "escalate_ticket", {"ticket_id": ticket["ticket_id"], "reason": "critical severity"}
        )

    text = (
        f"Destek talebiniz oluşturuldu: {ticket['ticket_id']} "
        f"(öncelik: {severity}, ekip: {ticket['assigned_to']}, durum: {ticket['status']})."
    )
    await call_tool("send_notification", {"user_id": user_id, "message": text, "channel": "email"})

    return {
        "current_agent": "ticket",
        "severity": severity,
        "ticket_id": ticket["ticket_id"],
        "ticket_status": ticket["status"],
        "escalated": ticket["escalated"],
        "messages": [AIMessage(content=text, name="ticket")],
    }
