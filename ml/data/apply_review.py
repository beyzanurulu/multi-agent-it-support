"""Apply a reviewer's decisions (ml/data/review_*.json) to a dataset.

Verified ids get verified=true and verified_by=<reviewer>; skipped ids are removed.
Run after clean.py so the reviewed text is the sanitised one, then run clean.py again.

    python ml/data/apply_review.py ml/data/clean.jsonl ml/data/review_claude.json ml/data/clean.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import read_jsonl, write_jsonl


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("review")
    p.add_argument("dst")
    args = p.parse_args()
    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    verified, skipped = set(review["verified"]), set(review["skipped"])
    out, marked = [], 0
    for row in read_jsonl(args.src):
        if row["id"] in skipped and not row.get("verified"):
            continue
        if row["id"] in verified and not row.get("verified"):
            row = {**row, "verified": True, "verified_by": review["reviewer"]}
            marked += 1
        out.append(row)
    write_jsonl(args.dst, out)
    print(f"verified {marked}, removed {len(skipped)}, kept {len(out)}")


if __name__ == "__main__":
    main()
