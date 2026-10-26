"""Train/val/test split (70/15/15). The test set contains only human-verified rows.

    python ml/data/split.py ml/data/clean.jsonl ml/data/splits
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import read_jsonl, write_jsonl


def split(rows: list[dict], seed: int = 7) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    verified = [r for r in rows if r.get("verified")]
    rest = [r for r in rows if not r.get("verified")]
    rng.shuffle(verified)
    rng.shuffle(rest)
    n_test = round(0.15 * len(rows))
    if len(verified) < n_test:
        print(f"warning: only {len(verified)} verified rows, test set is smaller than 15%",
              file=sys.stderr)
    test = verified[:n_test]
    pool = verified[n_test:] + rest
    rng.shuffle(pool)
    n_val = round(0.15 * len(rows))
    return {"train": pool[n_val:], "val": pool[:n_val], "test": test}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    for name, rows in split(read_jsonl(args.src)).items():
        write_jsonl(Path(args.out_dir) / f"{name}.jsonl", rows)
        print(f"{name}: {len(rows)}")


if __name__ == "__main__":
    main()
