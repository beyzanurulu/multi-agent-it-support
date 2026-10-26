"""Export the trained joint model to ONNX and apply dynamic int8 quantization.

    python ml/export_onnx.py ml/artifacts/berturk models/nlu
Output: model.onnx (quantized), tokenizer.json, labels.json -> served by nlu-service.
"""

import argparse
import json
import shutil
from pathlib import Path

import torch
from modeling import JointIntentNER
from onnxruntime.quantization import QuantType, quantize_dynamic
from transformers import AutoTokenizer


def export(src: Path, dst: Path, quantize: bool = True) -> Path:
    meta = json.loads((src / "labels.json").read_text())
    model = JointIntentNER(meta["encoder"], len(meta["intents"]), len(meta["bio_labels"]))
    model.load_state_dict(torch.load(src / "model.pt", map_location="cpu"))
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(src)
    sample = tokenizer(["Outlook açılmıyor"], return_tensors="pt")

    dst.mkdir(parents=True, exist_ok=True)
    fp32 = dst / "model.fp32.onnx"
    axes = {0: "batch", 1: "seq"}
    torch.onnx.export(
        model,
        (sample["input_ids"], sample["attention_mask"], sample["token_type_ids"]),
        str(fp32),
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["intent_logits", "ner_logits"],
        dynamic_axes={"input_ids": axes, "attention_mask": axes, "token_type_ids": axes,
                      "intent_logits": {0: "batch"}, "ner_logits": axes},
        opset_version=17,
        dynamo=False,
    )
    final = dst / "model.onnx"
    if quantize:
        quantize_dynamic(str(fp32), str(final), weight_type=QuantType.QInt8)
        fp32.unlink()
    else:
        fp32.rename(final)
    tokenizer.backend_tokenizer.save(str(dst / "tokenizer.json"))
    shutil.copy(src / "labels.json", dst / "labels.json")
    return final


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--no-quantize", action="store_true")
    args = p.parse_args()
    path = export(Path(args.src), Path(args.dst), quantize=not args.no_quantize)
    print(f"exported {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
