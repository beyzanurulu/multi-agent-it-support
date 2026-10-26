"""Evaluate NLU backends on the human-verified test set.

Backends: onnx (fine-tuned BERTurk), rules (keyword baseline), llm (few-shot).
Reports intent macro-F1 (multi-label), NER entity-F1 (seqeval), p95 latency, cost.

    python ml/evaluate.py ml/data/splits/test.jsonl --onnx models/nlu --llm \
        --report ml/reports/nlu_eval.md
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
from common import ENTITIES, INTENTS, ROOT, read_jsonl
from seqeval.metrics import classification_report as ner_report
from seqeval.metrics import f1_score as ner_f1
from sklearn.metrics import f1_score
from sklearn.preprocessing import MultiLabelBinarizer

sys.path.insert(0, str(ROOT / "services" / "nlu-service"))

LLM_PRICE_PER_1K_TOKENS = 0.00015 + 0.0006  # gpt-4o-mini input+output, rough upper bound


def word_bio(text: str, entities: list[dict]) -> list[str]:
    """Character spans -> whitespace-word BIO, so different tokenizers compare fairly."""
    tags = []
    for m in re.finditer(r"\S+", text):
        tag = "O"
        for e in entities:
            if m.start() < e["end"] and e["start"] < m.end():
                tag = ("B-" if m.start() <= e["start"] else "I-") + e["label"]
                break
        tags.append(tag)
    return tags


def llm_backend():
    from langchain_openai import ChatOpenAI
    from pydantic import BaseModel

    class Out(BaseModel):
        intents: list[str]
        entities: list[dict]

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(Out)
    system = (f"Türkçe IT destek mesajını analiz et. intents ⊂ {INTENTS} (birden fazla olabilir)."
              f" entities: [{{label, text}}], label ∈ {ENTITIES}. text mesajdaki ifadenin aynısı.")

    def analyze(text: str) -> dict:
        out = llm.invoke([("system", system), ("human", text)])
        ents = []
        for e in out.entities:
            idx = text.find(e.get("text", ""))
            if idx >= 0 and e.get("label") in ENTITIES:
                ents.append({"label": e["label"], "start": idx, "end": idx + len(e["text"])})
        return {"intents": [{"label": i, "score": 1.0} for i in out.intents if i in INTENTS],
                "entities": ents}
    return analyze


def evaluate(analyze, rows: list[dict]) -> dict:
    gold_i, pred_i, gold_t, pred_t, lat = [], [], [], [], []
    for row in rows:
        t0 = time.perf_counter()
        out = analyze(row["text"])
        lat.append((time.perf_counter() - t0) * 1000)
        gold_i.append(row["intents"])
        pred_i.append([i["label"] for i in out["intents"]])
        gold_t.append(word_bio(row["text"], row["entities"]))
        pred_t.append(word_bio(row["text"], out["entities"]))
    mlb = MultiLabelBinarizer(classes=INTENTS)
    y_true, y_pred = mlb.fit_transform(gold_i), mlb.transform(pred_i)
    return {
        "intent_macro_f1": round(float(f1_score(y_true, y_pred, average="macro",
                                                zero_division=0)), 4),
        "intent_exact_match": round(float(np.mean([set(g) == set(p)
                                                   for g, p in zip(gold_i, pred_i)])), 4),
        "ner_f1": round(float(ner_f1(gold_t, pred_t)), 4),
        "latency_p50_ms": round(float(np.percentile(lat, 50)), 2),
        "latency_p95_ms": round(float(np.percentile(lat, 95)), 2),
        "per_intent_f1": dict(zip(INTENTS, np.round(f1_score(
            y_true, y_pred, average=None, zero_division=0), 3).tolist())),
        "ner_report": ner_report(gold_t, pred_t, zero_division=0),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("test")
    p.add_argument("--onnx", help="exported model dir")
    p.add_argument("--llm", action="store_true", help="also run the LLM few-shot baseline")
    p.add_argument("--report", default="ml/reports/nlu_eval.md")
    args = p.parse_args()
    rows = read_jsonl(args.test)

    from nlu_service import rules

    backends = {"rules (keyword baseline)": rules.analyze}
    if args.onnx:
        from nlu_service.model import OnnxNLU

        backends["BERTurk fine-tuned (ONNX int8)"] = OnnxNLU(args.onnx).analyze
    if args.llm:
        backends["LLM few-shot (gpt-4o-mini)"] = llm_backend()

    results = {name: evaluate(fn, rows) for name, fn in backends.items()}
    lines = [(f"# NLU değerlendirmesi — test seti: {len(rows)} örnek "
             f"({sum(r.get('verified', False) for r in rows)} elle doğrulanmış)"), "",
             ("| Backend | Intent macro-F1 | Intent tam eşleşme | NER F1 | p50 ms | p95 ms |"
             " $/1k istek |"), "|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        cost = "≈%.2f" % (LLM_PRICE_PER_1K_TOKENS * 0.4 * 1000) if "LLM" in name else "0"
        lines.append(f"| {name} | {r['intent_macro_f1']} | {r['intent_exact_match']} | "
                     f"{r['ner_f1']} | {r['latency_p50_ms']} | {r['latency_p95_ms']} | {cost} |")
    for name, r in results.items():
        lines += ["", f"## {name}", "", "Intent F1:", "```",
                  json.dumps(r["per_intent_f1"], indent=1), "```", "NER:", "```",
                  r["ner_report"], "```"]
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:3 + len(results)]))


if __name__ == "__main__":
    main()
