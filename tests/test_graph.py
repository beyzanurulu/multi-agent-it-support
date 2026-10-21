import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.graph import build_graph
from src.agents.intent import classify_keywords
from src.agents.supervisor import route
from src.core.config import get_settings


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
    assert route({"intent": "x", "severity": "critical"}) == "ticket"
    assert route({"intent": "network", "proposed_solution": "s"}) == "end"
    assert route({"intent": "network", "proposed_solution": "s", "solution_accepted": False}) == "ticket"
    assert route({"intent": "network", "ticket_id": "INC-1"}) == "end"


def _run(app, text, thread="t1"):
    config = {"configurable": {"thread_id": thread}}
    return app.invoke({"messages": [HumanMessage(content=text)], "iteration_count": 0}, config)


def test_solution_then_accept():
    app = build_graph(checkpointer=MemorySaver())
    state = _run(app, "Şifremi unuttum")
    assert state["proposed_solution"] and not state.get("ticket_id")
    state = _run(app, "Teşekkürler, çözüldü")
    assert state["solution_accepted"] is True
    assert not state.get("ticket_id")


def test_solution_rejected_opens_ticket():
    app = build_graph(checkpointer=MemorySaver())
    _run(app, "VPN bağlanmıyor")
    state = _run(app, "Hâlâ bağlanmıyor")
    assert state["solution_accepted"] is False
    assert state["ticket_id"].startswith("INC-")


def test_critical_goes_straight_to_ticket():
    app = build_graph()
    state = app.invoke({"messages": [HumanMessage(content="Ransomware bulaştı!")]})
    assert state["escalated"] is True
    assert state["ticket_status"] == "escalated"
    assert not state.get("proposed_solution")


def test_unknown_intent_opens_ticket():
    app = build_graph()
    state = app.invoke({"messages": [HumanMessage(content="Merhaba, bir sorum var")]})
    assert state["ticket_id"]


def test_loop_guard(monkeypatch):
    monkeypatch.setenv("MAX_ITERATIONS", "2")
    get_settings.cache_clear()
    app = build_graph()
    state = app.invoke({"messages": [HumanMessage(content="Merhaba")]})
    assert state["iteration_count"] <= 3
    assert state["messages"][-1].name == "supervisor"
