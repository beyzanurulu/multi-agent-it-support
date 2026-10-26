import pytest
from fastapi.testclient import TestClient
from nlu_service import rules
from nlu_service.main import app
from nlu_service.model import decode_bio


def test_example_from_plan():
    text = ("Merhaba, Outlook açılmıyor 0x800CCC0E hatası veriyor, ayrıca VPN de bağlanmıyor. "
            "Muhasebe departmanındayım.")
    body = TestClient(app).post("/nlu", json={"text": text}).json()
    assert {i["label"] for i in body["intents"]} == {"email_issue", "vpn_issue"}
    ents = {(e["label"], e["text"]) for e in body["entities"]}
    assert {("YAZILIM", "Outlook"), ("HATA_KODU", "0x800CCC0E"), ("YAZILIM", "VPN"),
            ("DEPARTMAN", "Muhasebe")} <= ents


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Şifremi unuttum", "password_reset"),
        ("Hesabım kilitlendi", "account_locked"),
        ("Yazıcı kağıt sıkıştırıyor", "printer_issue"),
        ("Bu hafta muhasebeden kaç VPN ticket'ı geldi?", "report_request"),
        ("INC-10023 numaralı talebimin durumu ne?", "ticket_status"),
        ("Photoshop kurulumu lazım", "software_install"),
        ("Merhaba nasılsınız", "other"),
    ],
)
def test_rule_intents(text, intent):
    assert rules.classify_intents(text)[0]["label"] == intent


def test_rule_entities():
    ents = rules.extract_entities("Dün 10.0.0.15 IP'li laptopta Ayşe Yılmaz Teams'e giremedi")
    labels = {(e["label"], e["text"]) for e in ents}
    assert {("TARIH", "Dün"), ("IP_ADRESI", "10.0.0.15"), ("CIHAZ", "laptopta"),
            ("KISI", "Ayşe Yılmaz"), ("YAZILIM", "Teams")} <= labels


@pytest.mark.parametrize("text", ["VPN'e bağlanamıyorum, 809 hatası veriyor",
                                  "VPN hata 809 veriyor"])
def test_rule_numeric_error_code(text):
    assert ("HATA_KODU", "809") in {(e["label"], e["text"]) for e in rules.extract_entities(text)}


def test_decode_bio_merges_subwords():
    text = "Outlook açılmıyor"
    tags = ["O", "B-YAZILIM", "I-YAZILIM", "O", "O"]
    offsets = [(0, 0), (0, 3), (3, 7), (8, 17), (0, 0)]
    special = [1, 0, 0, 0, 1]
    assert decode_bio(text, tags, offsets, special) == [
        {"label": "YAZILIM", "start": 0, "end": 7, "text": "Outlook"}]


def test_health_reports_backend():
    assert TestClient(app).get("/health").json()["backend"] in ("rules", "onnx")
