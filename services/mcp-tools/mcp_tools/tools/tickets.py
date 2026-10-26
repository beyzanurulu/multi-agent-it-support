"""Ticket write tools. The agent layer only calls these after human approval."""

from psycopg.types.json import Jsonb

from mcp_tools.db import get_pool

TEAMS = {
    "account": "Service Desk L1", "vpn": "Network Team", "network": "Network Team",
    "email": "Messaging Team", "software": "Desktop Support", "hardware": "Desktop Support",
    "printer": "Desktop Support", "access": "IAM Team",
}
SEVERITIES = ("low", "medium", "high", "critical")


async def _audit(conn, actor: str, action: str, payload: dict) -> None:
    await conn.execute("INSERT INTO audit_log (actor, action, payload) VALUES (%s, %s, %s)",
                       (actor, action, Jsonb(payload)))


async def create_ticket(
    user_id: str, title: str, description: str, intent: str, category: str, severity: str,
    approved_by: str,
) -> dict:
    """Create a support ticket. `approved_by` records who approved the write."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    team = TEAMS.get(category, "Service Desk L1")
    async with get_pool().connection() as conn:
        row = await (await conn.execute(
            "INSERT INTO tickets (ticket_no, user_id, title, description, intent, category,"
            " severity, assigned_team) VALUES ('INC-' || nextval('ticket_no_seq'), %s, %s, %s,"
            " %s, %s, %s, %s) RETURNING id, ticket_no, status, severity, assigned_team",
            (user_id, title, description, intent, category, severity, team),
        )).fetchone()
        await conn.execute(
            "INSERT INTO ticket_events (ticket_id, event, detail, actor) VALUES (%s, 'created', "
            "%s, %s)", (row["id"], Jsonb({"approved_by": approved_by}), user_id))
        await _audit(conn, user_id, "create_ticket",
                     {"ticket_no": row["ticket_no"], "approved_by": approved_by})
    return {k: v for k, v in row.items() if k != "id"}


async def escalate_ticket(ticket_no: str, reason: str, approved_by: str) -> dict:
    """Escalate a ticket to L2 support."""
    async with get_pool().connection() as conn:
        row = await (await conn.execute(
            "UPDATE tickets SET status = 'escalated', assigned_team = 'IT Support L2', "
            "updated_at = now() WHERE ticket_no = %s "
            "RETURNING id, ticket_no, status, severity, assigned_team", (ticket_no,),
        )).fetchone()
        if row is None:
            raise ValueError(f"ticket {ticket_no} not found")
        await conn.execute(
            "INSERT INTO ticket_events (ticket_id, event, detail, actor) VALUES (%s, 'escalated',"
            " %s, %s)", (row["id"], Jsonb({"reason": reason}), approved_by))
        await _audit(conn, approved_by, "escalate_ticket", {"ticket_no": ticket_no})
    return {k: v for k, v in row.items() if k != "id"}


async def notify(user_id: str, message: str, channel: str = "email") -> dict:
    """Send a (mock) notification; it is only stored, never actually delivered."""
    if channel not in ("email", "sms", "teams"):
        raise ValueError("channel must be email, sms or teams")
    async with get_pool().connection() as conn:
        await conn.execute(
            "INSERT INTO notifications (user_id, channel, message) VALUES (%s, %s, %s)",
            (user_id, channel, message))
    return {"delivered": True, "channel": channel}
