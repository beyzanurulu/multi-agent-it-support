"""Rule-based NLU used until/unless the fine-tuned BERTurk ONNX model is present.

It is also the "keyword" baseline in ml/evaluate.py.
"""

import re

from nlu_service.labels import ENTITIES  # noqa: F401  (documents the label set)

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "password_reset": ("şifre", "sifre", "parola", "password", "sıfırla", "unuttum"),
    "account_locked": ("kilitlen", "kilitli", "locked", "hesabım açılmıyor", "giriş yapamıyorum"),
    "vpn_issue": ("vpn", "globalprotect", "uzak bağlantı", "evden bağlan"),
    "email_issue": ("outlook", "e-posta", "eposta", "mail", "posta kutusu", "0x800ccc0e"),
    "software_install": ("kur", "yükle", "install", "lisans", "kurulum", "setup"),
    "hardware_issue": ("laptop", "bilgisayar açılmıyor", "monitör", "ekran", "klavye", "mouse",
                       "fare", "pil", "şarj", "dock", "cihaz", "donanım", "ekipman", "bozuldu"),
    "network_issue": ("internet", "wifi", "wi-fi", "kablosuz", "ağ ", "dns", "bağlantı yok",
                      "ethernet"),
    "access_request": ("erişim", "yetki", "izin", "access", "klasör", "paylaşılan"),
    "printer_issue": ("yazıcı", "yazici", "printer", "çıktı", "toner", "kağıt"),
    "ticket_status": ("talebimin durum", "ticket durum", "inc-", "ne oldu", "durumu ne",
                      "ne aşamada", "ne durumda", "kapandı mı", "taleplerim"),
    "report_request": ("kaç ticket", "kaç talep", "rapor", "istatistik", "ortalama", "dağılım",
                       "en çok", "kaç tane", "çözüm süresi"),
}
# A report question mentions topics ("kaç VPN ticket'ı") without being that issue itself.
REPORT_MARKERS = ("kaç", "rapor", "istatistik", "ortalama", "dağılım", "en çok", "listele")
REPORT_SUBJECTS = r"ticket|talep|talebi|arıza|sorun|çözüm süresi"
DEASCII = str.maketrans("çğıöşü", "cgiosu")

SOFTWARE = ["Outlook", "Teams", "Excel", "Word", "PowerPoint", "Office", "VPN", "GlobalProtect",
            "SAP", "ERP", "Chrome", "Edge", "Adobe", "Photoshop", "Java", "OneDrive", "Zoom",
            "Windows", "SharePoint", "Visual Studio", "AutoCAD", "Slack"]
DEVICES = ["laptop", "dizüstü", "bilgisayar", "yazıcı", "monitör", "ekran", "klavye", "mouse",
           "fare", "telefon", "tablet", "dock", "docking station", "kulaklık", "kamera", "modem"]
DEPARTMENTS = ["Muhasebe", "Finans", "İnsan Kaynakları", "İK", "Satış", "Pazarlama", "Yazılım",
               "Operasyon", "Hukuk", "Satın Alma", "Müşteri Hizmetleri", "Bilgi İşlem"]
FIRST_NAMES = ["Ayşe", "Mehmet", "Zeynep", "Ahmet", "Elif", "Mustafa", "Fatma", "Emre", "Selin",
               "Burak", "Deniz", "Can", "Ece", "Kerem", "Merve", "Onur", "Gizem", "Hakan",
               "Tolga", "Ali", "Veli", "Esra", "Murat", "Cem"]
MONTHS = "ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık"

SUFFIX = r"(?:['’]?[a-zçğıöşü]*)"
PATTERNS: list[tuple[str, str]] = [
    ("HATA_KODU", r"\b0x[0-9a-fA-F]{6,8}\b|\bERR_[A-Z_]+\b|(?<=hata )\d{3,4}\b|\b\d{3,4}(?= [hH]ata)"),
    ("IP_ADRESI", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ("TARIH", (rf"\b\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}}\b|\b\d{{1,2}} (?:{MONTHS})\b|"
              r"\b(?:bugün|dün|yarın|bu sabah|dün akşam|geçen hafta|bu hafta|bu ay)\b")),
    ("YAZILIM", r"\b(?:" + "|".join(re.escape(s) for s in SOFTWARE) + r")" + SUFFIX + r"\b"),
    ("CIHAZ", r"\b(?:" + "|".join(re.escape(d) for d in DEVICES + [
        d.translate(str.maketrans("çğıöşü", "cgiosu")) for d in DEVICES]) + r")" + SUFFIX + r"\b"),
    ("DEPARTMAN", r"\b(?:" + "|".join(re.escape(d) for d in DEPARTMENTS) + r")" + SUFFIX + r"\b"),
    ("KISI", r"\b(?:" + "|".join(FIRST_NAMES) + r") [A-ZÇĞİÖŞÜ][a-zçğıöşü]+\b"),
]
COMPILED = [(label, re.compile(p, re.IGNORECASE if label in ("CIHAZ", "TARIH", "YAZILIM",
                                                              "DEPARTMAN") else 0))
            for label, p in PATTERNS]


def normalize(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def _close(a: str, b: str) -> bool:
    """Edit distance <= 1 (typos such as 'outlok', 'acilmiyor' vs 'açılmıyor')."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
            continue
        i += 1
        j += 1
    return edits + (len(b) - j) <= 1


def _matches(keyword: str, text: str, tokens: list[str]) -> bool:
    if keyword in text:
        return True
    plain = keyword.translate(DEASCII)
    if " " in keyword:
        return plain in text.translate(DEASCII)
    if len(keyword) < 5:
        # Short keywords ("pil", "ağ") must start a word, else "yapilir" would match "pil".
        return any(tok.startswith(plain) for tok in tokens)
    # Typo tolerance on word prefixes, so Turkish suffixes don't break the match.
    return any(_close(plain, tok[:len(plain)]) or _close(plain, tok[:len(plain) + 1])
               for tok in tokens if len(tok) >= len(plain) - 1)


def _strip_suffix(label: str, span: str) -> str:
    if label == "DEPARTMAN":
        # "muhasebeden" -> "muhasebe": keep the longest known department name as prefix.
        low = normalize(span)
        for dep in sorted(DEPARTMENTS, key=len, reverse=True):
            if low.startswith(normalize(dep)):
                return span[:len(dep)]
    if label in ("YAZILIM", "CIHAZ", "DEPARTMAN"):
        return re.split(r"['’]", span)[0]
    return span


def canonical_department(text: str) -> str | None:
    low = normalize(text)
    return next((d for d in DEPARTMENTS if normalize(d) == low), None)


def extract_entities(text: str) -> list[dict]:
    found: list[dict] = []
    taken: list[tuple[int, int]] = []
    for label, pattern in COMPILED:
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            if label == "DEPARTMAN" and m.group(0).lower().startswith("yazılım") and \
                    not re.search(r"yazılım (departman|ekib|biri)", text[start:end + 12].lower()):
                continue  # "yazılım kurmak" is not the software department
            if any(s < end and start < e for s, e in taken):
                continue
            value = _strip_suffix(label, m.group(0))
            end = start + len(value)
            taken.append((start, end))
            found.append({"label": label, "text": value, "start": start, "end": end})
    return sorted(found, key=lambda e: e["start"])


def classify_intents(text: str) -> list[dict]:
    t = normalize(text)
    tokens = re.findall(r"\w+", t.translate(DEASCII))
    scores: dict[str, float] = {}
    for intent, words in INTENT_KEYWORDS.items():
        hits = sum(1 for w in words if _matches(w, t, tokens))
        if hits:
            scores[intent] = min(0.6 + 0.15 * hits, 0.97)

    if any(m in t for m in REPORT_MARKERS) and re.search(REPORT_SUBJECTS, t):
        return [{"label": "report_request", "score": 0.95}]
    scores.pop("report_request", None)
    if "account_locked" in scores and "password_reset" in scores:
        scores.pop("password_reset" if "kilit" in t else "account_locked")
    if "software_install" in scores and len(scores) > 1 and not re.search(
            r"kur(ul|ab|mak|mam|un)|yükle|install|lisans", t):
        scores.pop("software_install")
    if not scores:
        return [{"label": "other", "score": 0.5}]
    return [{"label": k, "score": round(v, 2)}
            for k, v in sorted(scores.items(), key=lambda kv: -kv[1])]


def analyze(text: str) -> dict:
    return {"intents": classify_intents(text), "entities": extract_entities(text)}
