"""Tool tests against a migrated + seeded Postgres (see README: Geliştirme)."""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp_tools.server import mcp


@pytest.fixture(scope="module")
async def client():
    async with Client(mcp) as c:
        yield c


async def call(client, name, **args):
    result = await client.call_tool(name, args)
    data = result.structured_content
    return data["result"] if isinstance(data, dict) and set(data) == {"result"} else data


async def test_eight_tools_registered(client):
    names = {t.name for t in await client.list_tools()}
    assert names == {"search_kb", "create_ticket", "escalate_ticket", "notify", "get_user_info",
                     "check_system_status", "get_schema", "run_sql"}


@pytest.mark.parametrize(
    ("query", "kwargs", "expected"),
    [
        ("VPN bağlanmıyor", {}, "vpn_not_connecting"),
        ("Outlook açılmıyor hata veriyor", {"error_codes": ["0x800CCC0E"]}, "outlook_0x800ccc0e"),
        ("yazıcı kağıt sıkıştı", {"category": "printer"}, "printer_jam"),
        ("phishing e-postası geldi", {}, "phishing"),
    ],
)
async def test_hybrid_search(client, query, kwargs, expected):
    results = await call(client, "search_kb", query=query, **kwargs)
    assert results[0]["doc_id"] == expected


async def test_ticket_write_and_escalate(client):
    ticket = await call(client, "create_ticket", user_id="calisan", title="VPN sorunu",
                        description="bağlanmıyor", intent="vpn_issue", category="vpn",
                        severity="high", approved_by="calisan")
    assert ticket["assigned_team"] == "Network Team"
    escalated = await call(client, "escalate_ticket", ticket_no=ticket["ticket_no"],
                           reason="test", approved_by="uzman")
    assert escalated["status"] == "escalated"
    user = await call(client, "get_user_info", user_id="calisan")
    assert user["department"] == "Muhasebe"
    assert user["tickets"][0]["ticket_no"] == ticket["ticket_no"]


async def test_invalid_severity(client):
    with pytest.raises(ToolError):
        await call(client, "create_ticket", user_id="calisan", title="t", description="d",
                   intent="other", category="general", severity="urgent", approved_by="x")


async def test_status_and_notify(client):
    assert (await call(client, "check_system_status", service_name="fileserver"))["status"] == \
        "degraded"
    assert (await call(client, "notify", user_id="calisan", message="m"))["delivered"]


async def test_readonly_sql(client):
    schema = await call(client, "get_schema")
    assert "v_tickets" in schema and not any("email" in c for c in schema["v_tickets"])
    res = await call(client, "run_sql",
                     query="SELECT department, count(*) AS n FROM v_tickets GROUP BY department")
    assert res["row_count"] > 0
    res = await call(client, "run_sql", query="SELECT ticket_no FROM v_tickets")
    assert res["row_count"] == 200


@pytest.mark.parametrize(
    "query",
    ["SELECT email FROM users", "DELETE FROM v_tickets",
     "SELECT 1; DROP TABLE tickets", "SELECT * FROM tickets"],
)
async def test_readonly_role_blocks(client, query):
    with pytest.raises(ToolError):
        await call(client, "run_sql", query=query)
