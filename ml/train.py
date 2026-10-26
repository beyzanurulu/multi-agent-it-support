"""Fine-tune BERTurk for joint intent + NER, tracked in MLflow.

    python ml/train.py --train ml/data/splits/train.jsonl --val ml/data/splits/val.jsonl \
        --model dbmdz/bert-base-turkish-cased --epochs 4 --lr 3e-5 --out ml/artifacts/berturk
Runs on a Colab/Kaggle GPU in ~10 min for 3k samples; CPU works for smoke tests.
"""

import argparse
import json
import time
from pathlib import Path

import torch
from common import BIO_LABELS, INTENTS, read_jsonl
from modeling import JointIntentNER, encode, joint_loss
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoTokenizer, get_linear_schedule_with_warmup


def to_dataset(enc: dict) -> TensorDataset:
    keys = ["input_ids", "attention_mask", "token_type_ids", "intent_targets", "tags"]
    return TensorDataset(*[enc[k] for k in keys])


@torch.no_grad()
def val_loss(model, loader, device) -> float:
    model.eval()
    total, n = 0.0, 0
    for ids, mask, types, intents, tags in loader:
        il, nl = model(ids.to(device), mask.to(device), types.to(device))
        total += joint_loss(il, nl, intents.to(device), tags.to(device)).item() * len(ids)
        n += len(ids)
    model.train()
    return total / max(n, 1)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train", required=True)
    p.add_argument("--val", required=True)
    p.add_argument("--model", default="dbmdz/bert-base-turkish-cased")
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--lr", type=float, default=3e-5)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--max-len", type=int, default=96)
    p.add_argument("--ner-weight", type=float, default=1.0)
    p.add_argument("--out", default="ml/artifacts/berturk")
    p.add_argument("--experiment", default="nlu-berturk")
    p.add_argument("--no-mlflow", action="store_true")
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    train_ds = to_dataset(encode(tokenizer, read_jsonl(args.train), INTENTS, BIO_LABELS,
                                 args.max_len))
    val_ds = to_dataset(encode(tokenizer, read_jsonl(args.val), INTENTS, BIO_LABELS,
                               args.max_len))
    train_dl = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=args.batch_size)

    model = JointIntentNER(args.model, len(INTENTS), len(BIO_LABELS)).to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = len(train_dl) * args.epochs
    sched = get_linear_schedule_with_warmup(optim, int(0.1 * steps), steps)

    mlflow = None
    if not args.no_mlflow:
        import mlflow

        mlflow.set_experiment(args.experiment)
        mlflow.start_run()
        mlflow.log_params({k: v for k, v in vars(args).items() if k not in ("train", "val")})
        mlflow.log_params({"n_train": len(train_ds), "n_val": len(val_ds), "device": device})

    start, best = time.time(), float("inf")
    out = Path(args.out)
    for epoch in range(args.epochs):
        for ids, mask, types, intents, tags in train_dl:
            il, nl = model(ids.to(device), mask.to(device), types.to(device))
            loss = joint_loss(il, nl, intents.to(device), tags.to(device), args.ner_weight)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            optim.zero_grad()
        vl = val_loss(model, val_dl, device)
        print(f"epoch {epoch + 1}: train_loss={loss.item():.4f} val_loss={vl:.4f}")
        if mlflow:
            mlflow.log_metrics({"train_loss": loss.item(), "val_loss": vl}, step=epoch)
        if vl < best:
            best = vl
            out.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), out / "model.pt")

    tokenizer.save_pretrained(out)
    (out / "labels.json").write_text(json.dumps({
        "encoder": args.model, "intents": INTENTS, "bio_labels": BIO_LABELS,
        "max_len": args.max_len}, ensure_ascii=False, indent=1))
    if mlflow:
        mlflow.log_metrics({"best_val_loss": best, "train_minutes": (time.time() - start) / 60})
        mlflow.end_run()
    print(f"saved best model (val_loss={best:.4f}) -> {out}")


if __name__ == "__main__":
    main()
