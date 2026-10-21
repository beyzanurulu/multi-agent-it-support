"""IT support tool implementations backed by ChromaDB and the mock CRM."""

from src.memory import kb_loader
from src.tools import crm

SEVERITIES = ("low", "medium", "high", "critical")


async def search_knowledge_base(query: str, category: str | None = None) -> list[dict]:
    """Search the IT knowledge base for solutions. Optionally filter by category."""
    results = kb_loader.search(query, category=category)
    if category and not results:
        results = kb_loader.search(query)
    return results


async def create_ticket(
    user_id: str, title: str, description: str, severity: str, category: str
) -> dict:
    """Create a new support ticket and assign it to the responsible team."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    ticket_id = f"INC-{next(crm._counter)}"
    ticket = {
        "ticket_id": ticket_id,
        "user_id": user_id,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "assigned_to": crm.ASSIGNMENT.get(category, "Service Desk L1"),
        "status": "open",
        "escalated": False,
        "created_at": crm.now(),
        "history": [],
    }
    crm.TICKETS[ticket_id] = ticket
    return ticket


async def check_system_status(service_name: str) -> dict:
    """Check the operational status of a corporate service (vpn, email, sso...)."""
    status = crm.SYSTEM_STATUS.get(service_name.lower(), "unknown")
    return {"service": service_name.lower(), "status": status, "checked_at": crm.now()}


async def get_user_info(user_id: str) -> dict:
    """Get the user's profile and their previous tickets."""
    profile = crm.USERS.get(user_id, {"user_id": user_id, "name": "Bilinmeyen Kullanıcı",
                                      "department": None, "vip": False})
    tickets = [
        {"ticket_id": t["ticket_id"], "title": t["title"], "status": t["status"]}
        for t in crm.TICKETS.values()
        if t["user_id"] == user_id
    ]
    return {**profile, "tickets": tickets}


async def escalate_ticket(ticket_id: str, reason: str) -> dict:
    """Escalate a ticket to the next support level."""
    ticket = crm.TICKETS.get(ticket_id)
    if ticket is None:
        raise ValueError(f"ticket {ticket_id} not found")
    ticket.update(status="escalated", escalated=True, assigned_to="IT Support L2")
    ticket["history"].append({"event": "escalated", "reason": reason, "at": crm.now()})
    return ticket


async def send_notification(user_id: str, message: str, channel: str = "email") -> bool:
    """Send a (mock) notification to the user via email, sms or teams."""
    if channel not in ("email", "sms", "teams"):
        raise ValueError("channel must be email, sms or teams")
    crm.NOTIFICATIONS.append(
        {"user_id": user_id, "message": message, "channel": channel, "at": crm.now()}
    )
    return True


ALL_TOOLS = [
    search_knowledge_base,
    create_ticket,
    check_system_status,
    get_user_info,
    escalate_ticket,
    send_notification,
]
