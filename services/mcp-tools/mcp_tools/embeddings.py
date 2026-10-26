"""Text embeddings for the knowledge base (384 dimensions, matches kb_chunks.embedding)."""

import hashlib
import math
import re
from functools import lru_cache

from mcp_tools.config import get_settings

DIM = 384


class HashingEmbedder:
    """Offline, deterministic embedding (word + character trigram hashing).

    Used in tests/CI and when the multilingual model cannot be downloaded.
    """

    def _features(self, text: str) -> list[str]:
        words = re.findall(r"\w+", text.replace("İ", "i").lower())
        grams = [w[i:i + 3] for w in words if len(w) > 3 for i in range(len(w) - 2)]
        return words + grams

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * DIM
            for feat in self._features(text):
                h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
                vec[h % DIM] += 1.0 if (h >> 64) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class FastEmbedder:
    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]


@lru_cache
def get_embedder():
    settings = get_settings()
    if settings.embedding_provider == "fastembed":
        return FastEmbedder(settings.embedding_model)
    return HashingEmbedder()
