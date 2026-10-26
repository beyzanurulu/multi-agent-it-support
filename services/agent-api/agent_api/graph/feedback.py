"""Interpret the user's reply to a proposed solution."""

import re

NEGATIVE = ("olmadı", "olmadi", "çözülmedi", "çözemedi", "işe yaramadı", "ise yaramadi", "hâlâ",
            "hala", "devam ediyor", "değil", "aynı", "yine", "not", "still", "didn't",
            "doesn't", "no", "hayır", "maalesef")
POSITIVE = ("çözüldü", "cozuldu", "oldu", "teşekkür", "tesekkur", "işe yaradı", "düzeldi",
            "evet", "tamam", "süper", "harika", "solved", "fixed", "works", "thanks", "yes")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) for w in words)


def classify_feedback(text: str) -> bool | None:
    """True = solved, False = not solved, None = not a feedback message."""
    t = text.replace("İ", "i").lower()
    if _has(t, NEGATIVE):
        return False
    if _has(t, POSITIVE) or any(w in t for w in ("çözüldü", "teşekkür", "işe yaradı")):
        return True
    return None
