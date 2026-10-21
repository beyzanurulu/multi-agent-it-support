import pytest
from fastmcp.exceptions import ToolError

from src.tools import crm
from src.tools.server import call_tool, mcp


@pytest.fixture(autouse=True)
def clean_crm():
    crm.reset()


async def test_all_tools_registered():
    names = {t.name for t in await mcp.list_tools()}
    assert names == {
        "search_knowledge_base", "create_ticket", "check_system_status",
        "get_user_info", "escalate_ticket", "send_notification",
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("VPN bağlanmıyor", "vpn_not_connecting"),
        ("yazıcı kağıt sıkıştı", "printer_jam"),
        ("phishing e-postası geldi", "phishing"),
        ("outlook mail göndermiyor", "outlook_not_sending"),
    ],
)
async def test_kb_search(query, expected):
    results = await call_tool("search_knowledge_base", {"query": query})
    assert results[0]["id"] == expected


async def test_kb_has_50_plus_docs():
    from src.memory.kb_loader import get_collection

    assert get_collection().count() >= 50


async def test_ticket_lifecycle():
    ticket = await call_tool("create_ticket", {
        "user_id": "u001", "title": "VPN", "description": "bağlanmıyor",
        "severity": "high", "category": "network",
    })
    assert ticket["assigned_to"] == "Network Team"
    escalated = await call_tool("escalate_ticket", {"ticket_id": ticket["ticket_id"], "reason": "x"})
    assert escalated["status"] == "escalated"
    user = await call_tool("get_user_info", {"user_id": "u001"})
    assert user["tickets"][0]["ticket_id"] == ticket["ticket_id"]


async def test_invalid_severity_rejected():
    with pytest.raises(ToolError):
        await call_tool("create_ticket", {
            "user_id": "u001", "title": "t", "description": "d",
            "severity": "urgent", "category": "network",
        })


async def test_system_status_and_notification():
    status = await call_tool("check_system_status", {"service_name": "VPN"})
    assert status["status"] == "operational"
    assert await call_tool("send_notification", {"user_id": "u001", "message": "hi"}) is True
    assert crm.NOTIFICATIONS[-1]["channel"] == "email"
