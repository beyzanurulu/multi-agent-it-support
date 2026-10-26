"""Prompt-injection input classifier.

Weighted pattern scoring (Turkish + English). It is deliberately conservative:
blocked input never reaches an LLM, and write tools additionally need human
approval, so a miss here still cannot delete or modify data on its own.
"""

import re
from dataclasses import dataclass

PATTERNS: list[tuple[str, float]] = [
    ((r"(önceki|yukarıdaki|tüm|bütün)\s+(talimat|komut|kural|yönerge)\w*\s*(ları|leri)?\s*"
     r"(unut|yok say|görmezden gel|iptal)"), 1.0),
    (r"ignore\s+(all\s+|the\s+)?(previous|prior|above)\s+(instructions|rules|prompts?)", 1.0),
    (r"disregard\s+(all\s+|your\s+)?(previous\s+)?(instructions|rules)", 1.0),
    (r"(sistem|system)\s*(prompt|mesaj|talimat)\w*\s*(göster|yaz|ver|reveal|print|nedir)", 0.9),
    (r"(sen\s+artık|bundan\s+sonra\s+sen|you\s+are\s+now|act\s+as)\s+", 0.6),
    (r"(developer|geliştirici|admin|yönetici|god)\s*mod", 0.8),
    (r"jailbreak|\bDAN\b", 0.9),
    (r"(tüm|bütün|all)\s+(ticket|talep|kayıt|kullanıcı|veri)\w*\s*(sil|delete|drop|kaldır)", 1.0),
    (r"\b(drop|truncate|alter)\s+table\b|\bdelete\s+from\b|;\s*--", 0.9),
    (r"rolünü\s+(değiştir|unut)|role\s*[:=]\s*(admin|manager|yonetici)", 0.8),
    (r"(onay|approval)\s*(olmadan|gerekmeden|bypass|atla)", 0.8),
    (r"<\s*/?\s*(system|assistant|instructions?)\s*>", 0.8),
]
COMPILED = [(re.compile(p, re.IGNORECASE), w) for p, w in PATTERNS]
THRESHOLD = 0.8


@dataclass
class InjectionResult:
    blocked: bool
    score: float
    matches: list[str]


def check(text: str) -> InjectionResult:
    normalized = text.replace("İ", "i").replace("I", "ı")
    matches = [p.pattern for p, _ in COMPILED if p.search(normalized)]
    score = min(1.0, sum(w for p, w in COMPILED if p.pattern in matches))
    return InjectionResult(blocked=score >= THRESHOLD, score=round(score, 2), matches=matches)
