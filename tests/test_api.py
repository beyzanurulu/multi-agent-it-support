import pytest
from fastapi.testclient import TestClient

from src.api.deps import rate_limiter
from src.core.config import get_settings

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("CHECKPOINT_DB", str(tmp_path / "api.sqlite"))
    get_settings.cache_clear()
    rate_limiter.reset()
    from src.api.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_auth_required(client):
    assert client.post("/chat", json={"message": "VPN"}).status_code == 401


def test_rest_chat_flow(client):
    r = client.post("/chat", json={"message": "VPN bağlanmıyor", "user_id": "u001"}, headers=HEADERS)
    body = r.json()
    assert r.status_code == 200
    assert body["state"]["intent"] == "network"
    assert body["new_messages"][-1]["agent"] == "solution"

    sid = body["session_id"]
    body = client.post("/chat", json={"message": "olmadı", "session_id": sid}, headers=HEADERS).json()
    assert body["state"]["ticket_id"]
    assert client.get(f"/chat/{sid}", headers=HEADERS).json()["state"]["ticket_id"]

    trace = client.get(f"/admin/sessions/{sid}/trace", headers=HEADERS).json()
    agents = [s["agent"] for s in trace]
    assert {"triage", "solution", "ticket"} <= set(agents)
    assert any(t["ticket_id"] == body["state"]["ticket_id"]
               for t in client.get("/admin/tickets", headers=HEADERS).json())


def test_rest_approval_flow(client):
    body = client.post("/chat", json={"message": "Ransomware bulaştı"}, headers=HEADERS).json()
    sid = body["session_id"]
    assert body["pending_approval"]["type"] == "escalation_approval"
    assert client.post("/chat", json={"message": "?", "session_id": sid},
                       headers=HEADERS).status_code == 409

    body = client.post(f"/chat/{sid}/approval", json={"approved": True}, headers=HEADERS).json()
    assert body["state"]["escalated"] is True
    assert body["pending_approval"] is None


def test_websocket_streams_agent_steps(client):
    with client.websocket_connect("/ws/chat/ws1?api_key=test-key") as ws:
        ws.send_json({"message": "Şifremi unuttum", "user_id": "u001"})
        events = []
        while (event := ws.receive_json())["type"] != "done":
            events.append(event)
    agents = [e["agent"] for e in events if e["type"] == "agent_step"]
    assert agents[:3] == ["supervisor", "triage", "supervisor"]
    assert "solution" in agents
    assert event["state"]["proposed_solution"]


def test_websocket_approval(client):
    with client.websocket_connect("/ws/chat/ws2?api_key=test-key") as ws:
        ws.send_json({"message": "Phishing linkine tıkladım"})
        while (event := ws.receive_json())["type"] != "done":
            pass
        assert event["pending_approval"]
        ws.send_json({"type": "approval", "approved": True})
        while (event := ws.receive_json())["type"] != "done":
            pass
    assert event["state"]["escalated"] is True


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    get_settings.cache_clear()
    codes = [client.get("/admin/tickets", headers=HEADERS).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
