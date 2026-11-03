"""Train/val/test split held out by template.

Rows generated from the same template are near-duplicates, so a random split leaks the
test set into training and inflates F1. Instead ~15% of each intent's templates go to
test and ~15% to val; train only ever sees the remaining templates. A multi-intent row
lands in test/val only if all of its templates are held out there, and is dropped if it
mixes train and held-out templates.

The plan requires the test set to be human-verified. Unverified held-out rows are kept
out of test unless --allow-unverified-test is given (the split report says which).

    python ml/data/split.py ml/data/clean.jsonl ml/data/splits [--allow-unverified-test]
"""

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import read_jsonl, write_jsonl


def assign_templates(rows: list[dict], seed: int, share: float = 0.15) -> dict[str, str]:
    """Map each template id to 'train' | 'val' | 'test'."""
    rng = random.Random(seed)
    by_intent: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for tid in row.get("templates", []):
            by_intent[tid.split(":")[0]].add(tid)
    where: dict[str, str] = {}
    for intent in sorted(by_intent):
        tids = sorted(by_intent[intent], key=lambda t: int(t.split(":")[1]))
        rng.shuffle(tids)
        n = max(1, math.ceil(share * len(tids))) if len(tids) >= 3 else 0
        for i, tid in enumerate(tids):
            where[tid] = "test" if i < n else "val" if i < 2 * n else "train"
    return where


def split(rows: list[dict], seed: int = 7, allow_unverified_test: bool = False) -> dict:
    if not all(r.get("templates") for r in rows):
        raise SystemExit("rows without 'templates' ids: regenerate with ml/data/generate.py")
    where = assign_templates(rows, seed)
    out: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    stats = Counter()
    for row in rows:
        parts = {where[t] for t in row["templates"]}
        if len(parts) > 1:
            stats["dropped_mixed"] += 1
            continue
        part = parts.pop()
        if part == "test" and not row.get("verified") and not allow_unverified_test:
            stats["held_out_unverified"] += 1
            continue
        out[part].append(row)
    out["_report"] = {
        "templates": Counter(where.values()),
        "rows": {k: len(v) for k, v in out.items() if not k.startswith("_")},
        "test_verified": sum(r.get("verified", False) for r in out["test"]),
        "test_unverified_allowed": allow_unverified_test,
        **stats,
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("out_dir")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--allow-unverified-test", action="store_true",
                        help="use unverified held-out rows in test (report it as such)")
    args = parser.parse_args()
    parts = split(read_jsonl(args.src), args.seed, args.allow_unverified_test)
    report = parts.pop("_report")
    for name, rows in parts.items():
        write_jsonl(Path(args.out_dir) / f"{name}.jsonl", rows)
    (Path(args.out_dir) / "split_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not parts["test"]:
        print("warning: test set is empty - verify held-out rows in Label Studio or pass "
              "--allow-unverified-test", file=sys.stderr)


if __name__ == "__main__":
    main()
