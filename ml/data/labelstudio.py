"""Label Studio round trip.

export: JSONL -> Label Studio tasks with pre-labels (predictions) to correct by hand.
import: Label Studio JSON export -> JSONL with verified=true.

    python ml/data/labelstudio.py export ml/data/clean.jsonl ml/data/ls_tasks.json --n 600
    python ml/data/labelstudio.py import ls_export.json ml/data/verified.jsonl
    python ml/data/labelstudio.py merge ml/data/clean.jsonl ml/data/verified.jsonl ml/data/clean.jsonl
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import read_jsonl, write_jsonl


def to_task(row: dict) -> dict:
    result = [{"from_name": "intent", "to_name": "text", "type": "choices",
               "value": {"choices": row["intents"]}}]
    result += [{"from_name": "ner", "to_name": "text", "type": "labels",
                "value": {"start": e["start"], "end": e["end"],
                          "text": row["text"][e["start"]:e["end"]], "labels": [e["label"]]}}
               for e in row["entities"]]
    return {"data": {"id": row["id"], "text": row["text"]},
            "predictions": [{"model_version": row.get("source", "template"), "result": result}]}


def from_task(task: dict) -> dict | None:
    annotations = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
    if not annotations:
        return None
    intents, entities = [], []
    for item in annotations[-1]["result"]:
        if item["type"] == "choices":
            intents = item["value"]["choices"]
        elif item["type"] == "labels":
            v = item["value"]
            entities.append({"start": v["start"], "end": v["end"], "label": v["labels"][0]})
    return {"id": task["data"]["id"], "text": task["data"]["text"], "intents": intents,
            "entities": entities, "source": "label_studio", "verified": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("src")
    exp.add_argument("dst")
    exp.add_argument("--n", type=int, default=600)
    imp = sub.add_parser("import")
    imp.add_argument("src")
    imp.add_argument("dst")
    mrg = sub.add_parser("merge")
    mrg.add_argument("base")
    mrg.add_argument("verified")
    mrg.add_argument("dst")
    args = parser.parse_args()

    if args.cmd == "export":
        rows = read_jsonl(args.src)
        random.Random(3).shuffle(rows)
        tasks = [to_task(r) for r in rows[:args.n]]
        Path(args.dst).write_text(json.dumps(tasks, ensure_ascii=False, indent=1), "utf-8")
        print(f"exported {len(tasks)} tasks")
    elif args.cmd == "import":
        tasks = json.loads(Path(args.src).read_text("utf-8"))
        rows = [r for r in (from_task(t) for t in tasks) if r]
        write_jsonl(args.dst, rows)
        print(f"imported {len(rows)} verified rows")
    else:
        verified = {r["id"]: r for r in read_jsonl(args.verified)}
        merged = [verified.get(r["id"], r) for r in read_jsonl(args.base)]
        write_jsonl(args.dst, merged)
        print(f"merged: {sum(r.get('verified', False) for r in merged)} verified")


if __name__ == "__main__":
    main()
