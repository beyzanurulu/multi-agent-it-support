"""Smoke test of the full NLU pipeline with a tiny randomly initialised BERT.

Real training uses dbmdz/bert-base-turkish-cased on a GPU; this only proves the
generate -> clean -> split -> train -> export -> serve chain works offline.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

ML = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([sys.executable, *map(str, args)], check=True, cwd=ML.parent)


def make_tiny_encoder(path: Path, texts: list[str]) -> None:
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors, trainers
    from transformers import BertConfig, BertModel, BertTokenizerFast

    tok = Tokenizer(models.WordPiece(unk_token="[UNK]"))
    tok.normalizer = normalizers.BertNormalizer(lowercase=False)
    tok.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    tok.train_from_iterator(texts, trainers.WordPieceTrainer(
        vocab_size=800, special_tokens=["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]))
    tok.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 2), ("[SEP]", 3)])
    BertTokenizerFast(tokenizer_object=tok).save_pretrained(path)
    BertModel(BertConfig(vocab_size=tok.get_vocab_size(), hidden_size=64, num_hidden_layers=2,
                         num_attention_heads=2, intermediate_size=128)).save_pretrained(path)


def test_pipeline_end_to_end(tmp_path):
    raw, clean, splits = tmp_path / "raw.jsonl", tmp_path / "clean.jsonl", tmp_path / "splits"
    run(ML / "data/generate.py", "--n", "400", "--out", raw)
    rows = [json.loads(line) for line in raw.read_text().splitlines()]
    for row in rows[:80]:  # stand-in for Label Studio verified rows
        row["verified"] = True
    raw.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    run(ML / "data/clean.py", raw, clean, "--report", tmp_path / "report.md")
    run(ML / "data/split.py", clean, splits)
    assert all(json.loads(line)["verified"] for line in (splits / "test.jsonl").open())

    encoder = tmp_path / "tiny"
    make_tiny_encoder(encoder, [r["text"] for r in rows])
    run(ML / "train.py", "--train", splits / "train.jsonl", "--val", splits / "val.jsonl",
        "--model", encoder, "--epochs", "1", "--batch-size", "16", "--max-len", "48",
        "--out", tmp_path / "trained", "--no-mlflow")
    run(ML / "export_onnx.py", tmp_path / "trained", tmp_path / "onnx")

    from nlu_service.model import OnnxNLU

    out = OnnxNLU(tmp_path / "onnx").analyze("Outlook açılmıyor 0x800CCC0E hatası veriyor")
    assert out["intents"] and isinstance(out["entities"], list)

    run(ML / "evaluate.py", splits / "test.jsonl", "--onnx", tmp_path / "onnx",
        "--report", tmp_path / "eval.md")
    assert "BERTurk" in (tmp_path / "eval.md").read_text()
