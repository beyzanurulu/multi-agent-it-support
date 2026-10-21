"""In-memory mock CRM / ticketing backend (no real customer data)."""

import itertools
from datetime import UTC, datetime

USERS: dict[str, dict] = {
    "u001": {"user_id": "u001", "name": "Ayşe Yılmaz", "department": "Finans",
             "email": "ayse.yilmaz@example.local", "vip": False},
    "u002": {"user_id": "u002", "name": "Mehmet Demir", "department": "Satış",
             "email": "mehmet.demir@example.local", "vip": True},
    "u003": {"user_id": "u003", "name": "Zeynep Kaya", "department": "Yazılım",
             "email": "zeynep.kaya@example.local", "vip": False},
}

SYSTEM_STATUS: dict[str, str] = {
    "vpn": "operational",
    "email": "operational",
    "wifi": "operational",
    "sso": "operational",
    "fileserver": "degraded",
    "erp": "operational",
}

ASSIGNMENT = {
    "account": "Service Desk L1",
    "network": "Network Team",
    "software": "Desktop Support",
    "hardware": "Desktop Support",
    "email": "Messaging Team",
    "access": "IAM Team",
    "security": "Security Operations",
}

TICKETS: dict[str, dict] = {}
NOTIFICATIONS: list[dict] = []
_counter = itertools.count(1001)


def now() -> str:
    return datetime.now(UTC).isoformat()


def reset() -> None:
    TICKETS.clear()
    NOTIFICATIONS.clear()
