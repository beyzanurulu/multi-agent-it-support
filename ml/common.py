"""Shared helpers for the ml/ pipeline."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "nlu-service"))

from nlu_service.labels import BIO_LABELS, ENTITIES, INTENTS  # noqa: F401

DATA_DIR = Path(__file__).parent / "data"


def read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
