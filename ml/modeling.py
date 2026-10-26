"""Joint BERTurk model: multi-label intent head on [CLS] + token-classification NER head."""

import torch
from torch import nn
from transformers import AutoModel


class JointIntentNER(nn.Module):
    def __init__(self, encoder_name: str, n_intents: int, n_tags: int, dropout: float = 0.1):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(encoder_name)
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(dropout)
        self.intent_head = nn.Linear(hidden, n_intents)
        self.ner_head = nn.Linear(hidden, n_tags)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask,
                           token_type_ids=token_type_ids)
        seq = self.dropout(out.last_hidden_state)
        return self.intent_head(seq[:, 0]), self.ner_head(seq)


def joint_loss(intent_logits, ner_logits, intent_targets, tag_targets, ner_weight: float = 1.0):
    intent_loss = nn.functional.binary_cross_entropy_with_logits(intent_logits, intent_targets)
    ner_loss = nn.functional.cross_entropy(
        ner_logits.reshape(-1, ner_logits.size(-1)), tag_targets.reshape(-1), ignore_index=-100)
    return intent_loss + ner_weight * ner_loss


def encode(tokenizer, rows: list[dict], intents: list[str], bio: list[str], max_len: int) -> dict:
    """Tokenize and align character-span entities to sub-word BIO tags.

    Only the first sub-token of a word-piece run gets B-, continuation pieces of the
    same entity get I-; special tokens are ignored in the loss (-100).
    """
    enc = tokenizer([r["text"] for r in rows], truncation=True, max_length=max_len,
                    padding="max_length", return_offsets_mapping=True, return_tensors="pt")
    tag_index = {t: i for i, t in enumerate(bio)}
    intent_targets = torch.zeros(len(rows), len(intents))
    tags = torch.full(enc["input_ids"].shape, -100, dtype=torch.long)
    for i, row in enumerate(rows):
        for intent in row["intents"]:
            intent_targets[i, intents.index(intent)] = 1.0
        for j, (start, end) in enumerate(enc["offset_mapping"][i].tolist()):
            if start == end:
                continue
            tag = "O"
            for ent in row["entities"]:
                if start >= ent["start"] and end <= ent["end"]:
                    tag = ("B-" if start == ent["start"] else "I-") + ent["label"]
                    break
            tags[i, j] = tag_index[tag]
    enc.pop("offset_mapping")
    return {**enc, "intent_targets": intent_targets, "tags": tags}
