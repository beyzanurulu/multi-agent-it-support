"""End-to-end IT scenarios and routing accuracy (plan success criteria)."""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agents.graph import build_graph
from src.agents.intent import classify_keywords
from src.core.config import get_settings


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _say(app, thread, text, user_id="u001"):
    payload = {"messages": [HumanMessage(content=text)], "user_id": user_id, "iteration_count": 0}
    return await app.ainvoke(payload, {"configurable": {"thread_id": thread}})


# (scenario, first message, follow-up or None, expected KB doc, expects ticket)
SCENARIOS = [
    ("password", "Şifremi unuttum, giriş yapamıyorum", "teşekkürler çözüldü", "password_reset", False),
    ("software", "Bilgisayarıma Office kurulumu yapmam lazım", "olmadı", "office_install", True),
    ("network", "Evden VPN bağlanmıyor", "hâlâ bağlanmıyor", "vpn_not_connecting", True),
    ("printer", "Yazıcı kağıt sıkıştırıyor", "düzeldi teşekkürler", "printer_jam", False),
    ("email", "Outlook mail göndermiyor", "işe yaradı", "outlook_not_sending", False),
]


@pytest.mark.parametrize(("name", "first", "followup", "doc", "ticket"), SCENARIOS)
async def test_end_to_end_scenarios(name, first, followup, doc, ticket):
    app = build_graph(checkpointer=MemorySaver())
    state = await _say(app, name, first)
    assert doc in [r["id"] for r in state["kb_results"]]
    state = await _say(app, name, followup)
    assert bool(state.get("ticket_id")) is ticket
    assert state["iteration_count"] <= get_settings().max_iterations


async def test_security_scenario_with_approval():
    app = build_graph(checkpointer=MemorySaver())
    state = await _say(app, "sec", "Şüpheli bir e-postadaki linke tıkladım, virüs olabilir")
    assert state["__interrupt__"]
    state = await app.ainvoke(Command(resume={"approved": True}),
                              {"configurable": {"thread_id": "sec"}})
    assert state["escalated"] is True


LABELLED = [
    ("Şifremin süresi dolmuş", "password_reset"),
    ("Hesabım kilitlendi", "password_reset"),
    ("Parolamı sıfırlamak istiyorum", "password_reset"),
    ("Visual Studio yüklemem gerekiyor", "software_install"),
    ("Adobe lisansı lazım", "software_install"),
    ("Yazılım güncellemesi hata veriyor", "software_install"),
    ("Wi-Fi'a bağlanamıyorum", "network"),
    ("İnternet çok yavaş", "network"),
    ("DNS çözümlemiyor", "network"),
    ("Monitör görüntü vermiyor", "hardware"),
    ("Klavyem çalışmıyor", "hardware"),
    ("Laptop çok ısınıyor", "hardware"),
    ("Outlook açılmıyor", "email"),
    ("E-posta kutum doldu", "email"),
    ("Finans klasörüne erişim istiyorum", "access_request"),
    ("Yetki talebim var", "access_request"),
    ("Bilgisayarımda virüs var", "security_incident"),
    ("Phishing maili aldım", "security_incident"),
    ("Merhaba", "other"),
    ("VPN sertifika hatası", "network"),
]


def test_routing_accuracy_at_least_90_percent():
    correct = sum(classify_keywords(text).intent == label for text, label in LABELLED)
    assert correct / len(LABELLED) >= 0.9, f"{correct}/{len(LABELLED)}"
