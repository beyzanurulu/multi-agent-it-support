import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.graph import build_graph
from src.agents.intent import classify_keywords
from src.agents.supervisor import route
from src.core.config import get_settings
from src.memory.checkpointer import sqlite_checkpointer


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("text", "intent", "severity"),
    [
        ("Şifremi unuttum, hesabım kilitlendi", "password_reset", "medium"),
        ("Bilgisayarıma Photoshop kurulumu lazım", "software_install", "low"),
        ("VPN bağlanmıyor, acil çalışamıyorum", "network", "high"),
        ("Phishing linkine tıkladım", "security_incident", "critical"),
        ("Yazıcı kağıt sıkıştırıyor", "hardware", "medium"),
        ("Outlook mail göndermiyor", "email", "medium"),
        ("Merhaba", "other", "low"),
    ],
)
def test_keyword_classifier(text, intent, severity):
    result = classify_keywords(text)
    assert (result.intent, result.severity) == (intent, severity)


def test_route_table():
    assert route({}) == "triage"
    assert route({"intent": "network", "severity": "medium"}) == "solution"
    assert route({"intent": "x", "severity": "critical"}) == "human_approval"
    assert route({"intent": "x", "severity": "critical", "approval_status": "approved"}) == "ticket"
    assert route({"intent": "network", "proposed_solution": "s"}) == "end"
    assert route({"intent": "network", "proposed_solution": "s", "solution_accepted": False}) == "ticket"
    assert route({"intent": "network", "ticket_id": "INC-1"}) == "end"


async def _run(app, text, thread="t1", user_id="u001"):
    config = {"configurable": {"thread_id": thread}}
    payload = {"messages": [HumanMessage(content=text)], "user_id": user_id, "iteration_count": 0}
    return await app.ainvoke(payload, config)


async def test_solution_then_accept():
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "Şifremi unuttum")
    assert state["proposed_solution"] and not state.get("ticket_id")
    assert state["kb_results"][0]["category"] == "account"
    state = await _run(app, "Teşekkürler, çözüldü")
    assert state["solution_accepted"] is True
    assert not state.get("ticket_id")


async def test_solution_rejected_opens_ticket():
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "VPN bağlanmıyor")
    assert state["kb_results"][0]["id"] == "vpn_not_connecting"
    state = await _run(app, "Hâlâ bağlanmıyor")
    assert state["solution_accepted"] is False
    assert state["ticket_id"].startswith("INC-")


async def test_critical_requires_human_approval():
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "Ransomware bulaştı!", thread="crit")
    assert state["__interrupt__"][0].value["type"] == "escalation_approval"
    assert not state.get("ticket_id")

    state = await app.ainvoke(
        Command(resume={"approved": True}), {"configurable": {"thread_id": "crit"}}
    )
    assert state["approval_status"] == "approved"
    assert state["escalated"] is True
    assert state["ticket_status"] == "escalated"
    assert not state.get("proposed_solution")


async def test_rejected_approval_opens_normal_ticket():
    app = build_graph(checkpointer=MemorySaver())
    await _run(app, "Phishing linkine tıkladım", thread="rej")
    state = await app.ainvoke(
        Command(resume={"approved": False}), {"configurable": {"thread_id": "rej"}}
    )
    assert state["approval_status"] == "rejected"
    assert state["severity"] == "high"
    assert state["escalated"] is False
    assert state["ticket_id"]


@pytest.mark.parametrize(
    ("reply", "accepted"),
    [("Teşekkürler, çözüldü", True), ("evet oldu", True), ("olmadı", False),
     ("hâlâ çalışmıyor", False), ("çözülmedi", False), ("işe yaramadı", False)],
)
async def test_feedback_detection(reply, accepted):
    app = build_graph(checkpointer=MemorySaver())
    await _run(app, "Şifremi unuttum", thread=reply)
    state = await _run(app, reply, thread=reply)
    assert state["solution_accepted"] is accepted
    assert bool(state.get("ticket_id")) is (not accepted)


async def test_sqlite_checkpointer_persists_conversation(tmp_path):
    db = str(tmp_path / "cp.sqlite")
    async with sqlite_checkpointer(db) as saver:
        await _run(build_graph(checkpointer=saver), "VPN bağlanmıyor", thread="persist")
    # A fresh connection (e.g. after restart) continues the same conversation.
    async with sqlite_checkpointer(db) as saver:
        state = await _run(build_graph(checkpointer=saver), "olmadı", thread="persist")
    assert state["intent"] == "network"
    assert state["ticket_id"]


async def test_unknown_intent_opens_ticket():
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "Merhaba, bir sorum var")
    assert state["ticket_id"]


async def test_service_outage_opens_ticket():
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "fileserver klasörlerine ulaşamıyorum")
    assert state["ticket_id"] and not state.get("proposed_solution")


async def test_vip_user_severity_bumped():
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "Bana insan lazım, Outlook çalışmıyor", user_id="u002")
    assert state["severity"] == "high"


async def test_loop_guard(monkeypatch):
    monkeypatch.setenv("MAX_ITERATIONS", "2")
    get_settings.cache_clear()
    app = build_graph(checkpointer=MemorySaver())
    state = await _run(app, "Merhaba")
    assert state["iteration_count"] <= 3
    assert state["messages"][-1].name == "supervisor"
