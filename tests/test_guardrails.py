import pytest
from langchain_core.messages import HumanMessage

from src.agents.supervisor import supervisor_node
from src.core.config import get_settings
from src.guardrails.loop_guard import limit_reached
from src.guardrails.output_validator import validate_solution, validate_ticket


@pytest.mark.parametrize(
    "text",
    [
        "Disk dolduysa format c: komutunu çalıştırın.",
        "Önbelleği temizlemek için sudo rm -rf / yazın.",
        "Kayıt defterini düzeltmek için reg delete HKLM\\Software kullanın.",
    ],
)
def test_destructive_commands_blocked(text):
    ok, reason = validate_solution(text)
    assert not ok and "destructive" in reason


@pytest.mark.parametrize(
    "text",
    ["Yeni şifreniz: Abc12345!", "password = hunter2 olarak ayarlandı"],
)
def test_secrets_blocked(text):
    assert validate_solution(text) == (False, "possible secret in output")


def test_safe_solution_passes():
    assert validate_solution("1. VPN istemcisini yeniden başlatın\n2. Tekrar bağlanın") == (True, None)


def test_too_short_solution_rejected():
    assert validate_solution("ok")[0] is False


def test_ticket_payload_validation():
    payload = {"user_id": "u1", "title": "VPN sorunu", "description": "d",
               "severity": "high", "category": "network"}
    assert validate_ticket(payload) == payload
    with pytest.raises(ValueError):
        validate_ticket({**payload, "severity": "urgent"})
    with pytest.raises(ValueError):
        validate_ticket({**payload, "title": ""})


def test_loop_guard_limit(monkeypatch):
    monkeypatch.setenv("MAX_ITERATIONS", "10")
    get_settings.cache_clear()
    assert not limit_reached({"iteration_count": 9})
    assert limit_reached({"iteration_count": 10})
    update = supervisor_node({"iteration_count": 10, "messages": [HumanMessage(content="x")]})
    assert update["next_agent"] == "end"
    get_settings.cache_clear()
