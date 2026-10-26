"""ONNX Runtime inference for the fine-tuned BERTurk joint intent + NER model.

Expected files in MODEL_DIR (produced by ml/export_onnx.py):
  model.onnx (quantized), tokenizer.json, labels.json
"""

import json
from pathlib import Path

import numpy as np

from nlu_service.labels import BIO_LABELS, INTENTS


class OnnxNLU:
    def __init__(self, model_dir: str | Path, intent_threshold: float = 0.5) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = Path(model_dir)
        meta = json.loads((model_dir / "labels.json").read_text())
        self.intents: list[str] = meta.get("intents", INTENTS)
        self.bio: list[str] = meta.get("bio_labels", BIO_LABELS)
        self.max_len: int = meta.get("max_len", 128)
        self.threshold = intent_threshold
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tokenizer.enable_truncation(self.max_len)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(model_dir / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.input_names = {i.name for i in self.session.get_inputs()}

    def analyze(self, text: str) -> dict:
        enc = self.tokenizer.encode(text)
        feeds = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
        intent_logits, ner_logits = self.session.run(["intent_logits", "ner_logits"], feeds)

        probs = 1 / (1 + np.exp(-intent_logits[0]))
        intents = [{"label": self.intents[i], "score": round(float(p), 3)}
                   for i, p in enumerate(probs) if p >= self.threshold]
        if not intents:
            best = int(probs.argmax())
            intents = [{"label": self.intents[best], "score": round(float(probs[best]), 3)}]
        intents.sort(key=lambda x: -x["score"])

        tags = [self.bio[i] for i in ner_logits[0].argmax(-1)]
        return {"intents": intents, "entities": decode_bio(text, tags, enc.offsets,
                                                           enc.special_tokens_mask)}


def decode_bio(text: str, tags: list[str], offsets, special_mask) -> list[dict]:
    """Merge BIO tags over sub-word offsets into character spans."""
    entities: list[dict] = []
    current = None
    for tag, (start, end), special in zip(tags, offsets, special_mask):
        if special or start == end:
            continue
        if tag.startswith("B-") or (tag.startswith("I-") and
                                    (current is None or current["label"] != tag[2:])):
            if current:
                entities.append(current)
            current = {"label": tag[2:], "start": start, "end": end}
        elif tag.startswith("I-") and current:
            current["end"] = end
        else:
            if current:
                entities.append(current)
            current = None
    if current:
        entities.append(current)
    for ent in entities:
        ent["text"] = text[ent["start"]:ent["end"]]
    return entities
