import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from agent_api.main import app

    with TestClient(app) as c:
        yield c


def login(client, user):
    r = client.post("/auth/login", json={"user_id": user, "password": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_login_rejects_bad_password(client):
    assert client.post("/auth/login", json={"user_id": "calisan", "password": "x"}).status_code \
        == 401


def test_chat_requires_token(client):
    assert client.post("/chat", json={"message": "VPN"}).status_code == 401


def test_rest_flow_with_approval(client):
    h = login(client, "calisan")
    body = client.post("/chat", json={"message": "Yazıcı kağıt sıkıştırıyor, TC 10000000146"},
                       headers=h).json()
    sid = body["session_id"]
    assert any(e["type"] == "guardrail" and e["kind"] == "pii" for e in body["events"])
    assert any(e["type"] == "nlu" for e in body["events"])
    assert any(e["type"] == "tool_call" and e["tool"] == "search_kb" for e in body["events"])
    assert body["messages"][-1]["agent"] == "solution"

    body = client.post("/chat", json={"message": "olmadı", "session_id": sid}, headers=h).json()
    assert body["pending_approval"]["type"] == "ticket_approval"
    assert any(e["type"] == "interrupt" and e["kind"] == "ticket_approval" for e in body["events"])
    assert "10000000146" not in body["pending_approval"]["draft"]["description"]

    body = client.post(f"/chat/{sid}/resume", json={"approved": True}, headers=h).json()
    assert body["tickets"][0]["ticket_no"].startswith("INC-")


def test_sessions_are_isolated_per_user(client):
    h1, h2 = login(client, "calisan"), login(client, "uzman")
    sid = client.post("/chat", json={"message": "VPN bağlanmıyor"}, headers=h1).json()["session_id"]
    assert client.get(f"/chat/{sid}", headers=h2).json()["plan"] == []


def test_websocket_streams_steps(client):
    token = login(client, "yonetici")["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/chat/s-ws?token={token}") as ws:
        ws.send_json({"message": "Bu hafta muhasebeden kaç VPN ticket'ı geldi?"})
        events = []
        while (event := ws.receive_json())["type"] != "done":
            events.append(event)
    types = [e["type"] for e in events]
    assert types[0] == "nlu" and "sql" in types and "tool_call" in types
    assert events[-1]["agent"] == "analytics"


def test_metrics_exposed(client):
    assert "agent_tool_calls_total" in client.get("/metrics/").text
