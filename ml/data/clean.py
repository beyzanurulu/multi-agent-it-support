"""Deduplicate, validate spans and write a class-balance report.

    python ml/data/clean.py ml/data/raw.jsonl ml/data/clean.jsonl
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ENTITIES, INTENTS, read_jsonl, write_jsonl


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
    seen, kept, stats = set(), [], Counter()
    # Verified rows win over unverified duplicates.
    for row in sorted(rows, key=lambda r: not r.get("verified", False)):
        if not valid(row):
            stats["invalid"] += 1
            continue
        key = norm(row["text"])
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append(row)
    return kept, dict(stats)


def report(rows: list[dict], stats: dict) -> str:
    intents = Counter(i for r in rows for i in r["intents"])
    ents = Counter(e["label"] for r in rows for e in r["entities"])
    lines = ["# Veri kalitesi raporu", "", f"- Örnek: {len(rows)}",
             f"- Doğrulanmış: {sum(r.get('verified', False) for r in rows)}",
             f"- Çoklu niyet: {sum(len(r['intents']) > 1 for r in rows)}",
             f"- Atılan: {stats}", "", "## Intent dağılımı", "", "| Intent | n | % |", "|---|---|---|"]
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
    print(f"kept {len(rows)} rows, dropped {stats}")


if __name__ == "__main__":
    main()
