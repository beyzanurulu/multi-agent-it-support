"""Deduplicate, validate spans and write a class-balance report.

    python ml/data/clean.py ml/data/raw.jsonl ml/data/clean.jsonl
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENTITIES, INTENTS, read_jsonl, write_jsonl
from generate import TEMPLATES, VALUES, slot_values

# --- LLM paraphrase sanitising -------------------------------------------------------
# Local models often wrap the answer in chat ("Tabii, işte...", "Talep: ..."), answer in
# another language/script, or ramble across several lines. Keep the one line that is the
# paraphrase; drop the row when there is none.
FOREIGN_SCRIPT = re.compile(r"[\u0400-\u04ff\u0590-\u06ff\u3040-\u9fff\uac00-\ud7af]")
LABEL_PREFIX = re.compile(r"^\s*(?:yeni\s+)?(?:talep|istek|metin|cevap|yanıt)\s*:\s*", re.IGNORECASE)
CHATTER = re.compile(
    r"^(tabii|elbette|evet|işte|tamam|memnuniyetle|anladım)\b|yeniden yaz|farklı kelime|"
    r"sadece yeni metni|orijinal talep|ifadeleri koru|bu cümle|talebiniz budur|"
    r"şekilde yazılmış|bir farklı dil", re.IGNORECASE)
MAX_LEN = 200


def sanitize_llm(row: dict) -> dict | None:
    text = row["text"]
    if FOREIGN_SCRIPT.search(text) or "```" in text:
        return None
    values = [(e, text[e["start"]:e["end"]]) for e in row["entities"]]
    for line in text.splitlines():
        line = LABEL_PREFIX.sub("", line.strip()).strip(' "“”\'')
        if not line or CHATTER.search(line) or len(line) > MAX_LEN or len(line) < 6:
            continue
        entities, ok = [], True
        for ent, value in values:
            idx = line.find(value)
            if idx < 0:
                ok = False
                break
            entities.append({**ent, "start": idx, "end": idx + len(value)})
        if ok:
            return {**row, "text": line, "entities": entities}
    return None


def slots_ok(row: dict) -> bool:
    """Entity values must fit the template they were generated for (see generate.py)."""
    for tid in row.get("templates", []):
        intent, idx = tid.split(":")
        template = TEMPLATES[intent][int(idx)]
        for ent in row["entities"]:
            if "{" + ent["label"] + "}" not in template:
                continue
            allowed = {v.lower() for v in slot_values(intent, template, ent["label"])}
            value = row["text"][ent["start"]:ent["end"]].lower()
            if value not in allowed and not any(value == v.translate(DEASCII_LOWER)
                                                 for v in allowed):
                if any(e["label"] == ent["label"] for e in row["entities"] if e is not ent):
                    continue  # multi-intent: the value may belong to the other template
                return False
    return True


DEASCII_LOWER = str.maketrans("çğıöşü", "cgiosu")

# --- Gazetteer pass --------------------------------------------------------------------
# Templates contain fixed words ("GlobalProtect bağlanıyor", "Outlook arama çalışmıyor",
# "yazıcı ...") that are software/devices but were never slots, so they had no entity.
# Tag every known name that is not already covered. Suffixes stay outside the span
# ("Outlook'ta" -> "Outlook", "yazıcıda" -> "yazıcı"), matching the labeling guideline.
GAZETTEER = {
    "YAZILIM": sorted(set(VALUES["YAZILIM"]) | {"SharePoint", "Software Center",
                                                "GlobalProtect", "VPN", "Outlook"},
                      key=len, reverse=True),
    "CIHAZ": sorted(set(VALUES["CIHAZ"]), key=len, reverse=True),
}


def _gazetteer_pattern(label: str, name: str) -> re.Pattern:
    tail = r"(?![A-Za-zÇĞİÖŞÜçğıöşü])" if label == "YAZILIM" else ""
    return re.compile(r"(?<![A-Za-zÇĞİÖŞÜçğıöşü])" + re.escape(name) + tail, re.IGNORECASE)


GAZETTEER_RE = [(label, _gazetteer_pattern(label, name))
                for label, names in GAZETTEER.items() for name in names]


def add_missing_entities(row: dict) -> dict:
    entities = list(row["entities"])
    taken = [(e["start"], e["end"]) for e in entities]
    added = False
    for label, pattern in GAZETTEER_RE:
        for m in pattern.finditer(row["text"]):
            if any(s < m.end() and m.start() < e for s, e in taken):
                continue
            entities.append({"start": m.start(), "end": m.end(), "label": label})
            taken.append((m.start(), m.end()))
            added = True
    if not added:
        return row
    return {**row, "entities": sorted(entities, key=lambda e: e["start"])}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip(" .,!?")


def valid(row: dict) -> bool:
    if not row["intents"] or any(i not in INTENTS for i in row["intents"]):
        return False
    spans = sorted((e["start"], e["end"]) for e in row["entities"])
    if any(e["label"] not in ENTITIES for e in row["entities"]):
        return False
    if any(s < 0 or e > len(row["text"]) or s >= e for s, e in spans):
        return False
    return all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))


def clean(rows: list[dict]) -> tuple[list[dict], dict]:
    seen, kept, stats, trimmed = set(), [], Counter(), 0
    # Verified rows win over unverified duplicates.
    for row in sorted(rows, key=lambda r: not r.get("verified", False)):
        if row.get("source") == "llm" and not row.get("verified"):
            fixed = sanitize_llm(row)
            if fixed is None:
                stats["llm_unusable"] += 1
                continue
            if fixed["text"] != row["text"]:
                trimmed += 1
            row = fixed
        if not valid(row):
            stats["invalid"] += 1
            continue
        tagged = add_missing_entities(row)
        if tagged is not row:
            stats["entities_added"] += 1
            row = tagged
        if not row.get("verified") and not slots_ok(row):
            stats["slot_mismatch"] += 1
            continue
        key = norm(row["text"])
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append(row)
    stats["llm_trimmed"] = trimmed
    return kept, dict(stats)


INFO_STATS = ("llm_trimmed", "entities_added")


def report(rows: list[dict], stats: dict) -> str:
    intents = Counter(i for r in rows for i in r["intents"])
    ents = Counter(e["label"] for r in rows for e in r["entities"])
    lines = ["# Veri kalitesi raporu", "", f"- Örnek: {len(rows)}",
             f"- Doğrulanmış: {sum(r.get('verified', False) for r in rows)}",
             f"- Çoklu niyet: {sum(len(r['intents']) > 1 for r in rows)}",
             f"- Farklı şablon: {len({t for r in rows for t in r.get('templates', [])})}",
             f"- LLM ile yeniden ifade edilmiş: {sum(r.get('source') == 'llm' for r in rows)}",
             f"- Atılan: { {k: v for k, v in stats.items() if k not in INFO_STATS} }",
             f"- LLM sohbet artığından temizlenen: {stats.get('llm_trimmed', 0)}",
             f"- Gazetteer ile eksik entity eklenen: {stats.get('entities_added', 0)}", "", "## Intent dağılımı", "", "| Intent | n | % |", "|---|---|---|"]
    total = sum(intents.values())
    lines += [f"| {k} | {intents.get(k, 0)} | {100 * intents.get(k, 0) / total:.1f} |"
              for k in INTENTS]
    lines += ["", "## Entity dağılımı", "", "| Entity | n |", "|---|---|"]
    lines += [f"| {k} | {ents.get(k, 0)} |" for k in ENTITIES]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--report", default=str(Path(__file__).parents[1] / "reports" /
                                                 "data_report.md"))
    args = parser.parse_args()
    rows, stats = clean(read_jsonl(args.src))
    write_jsonl(args.dst, rows)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(report(rows, stats), encoding="utf-8")
    dropped = {k: v for k, v in stats.items() if k not in INFO_STATS}
    print(f"kept {len(rows)} rows, dropped {dropped}, trimmed {stats.get('llm_trimmed', 0)}, "
          f"entities added to {stats.get('entities_added', 0)}")


if __name__ == "__main__":
    main()
