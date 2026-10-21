"""Loads the markdown knowledge base into ChromaDB and searches it.

Embeddings: OpenAI `text-embedding-3-small` when an API key is configured,
otherwise a local hashing embedding (word + character trigram features) so the
system runs offline at zero cost.
"""

import hashlib
import math
import re
from functools import lru_cache
from pathlib import Path

import chromadb
import structlog
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings

from src.core.config import get_settings

log = structlog.get_logger()
COLLECTION = "it_knowledge_base"


class HashingEmbedding(EmbeddingFunction[Documents]):
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    @staticmethod
    def name() -> str:
        return "hashing"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    @staticmethod
    def build_from_config(config: dict) -> "HashingEmbedding":
        return HashingEmbedding(**config)

    def _features(self, text: str) -> list[str]:
        words = re.findall(r"\w+", text.lower())
        grams = [w[i:i + 3] for w in words if len(w) > 3 for i in range(len(w) - 2)]
        return words + grams

    def __call__(self, input: Documents) -> Embeddings:
        vectors = []
        for text in input:
            vec = [0.0] * self.dim
            for feat in self._features(text):
                h = int(hashlib.md5(feat.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


def _embedding_function() -> EmbeddingFunction:
    settings = get_settings()
    if settings.llm_enabled:
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        return OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key, model_name="text-embedding-3-small"
        )
    return HashingEmbedding()


def parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    category = "general"
    if match := re.match(r"---\s*\ncategory:\s*(\w+)\s*\n---\s*\n", text):
        category = match.group(1)
        text = text[match.end():]
    title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    return {"id": path.stem, "title": title, "category": category, "content": text.strip()}


def load_documents(kb_path: str | Path) -> list[dict]:
    return [parse_doc(p) for p in sorted(Path(kb_path).glob("*.md"))]


def embedding_text(doc: dict) -> str:
    """Title is weighted twice; the shared "when to open a ticket" footer is dropped."""
    body = doc["content"].split("## Ne Zaman Talep Açılmalı")[0]
    return f"{doc['title']}\n{doc['title']}\n{body}"


@lru_cache
def get_collection() -> chromadb.Collection:
    settings = get_settings()
    chroma_settings = ChromaSettings(anonymized_telemetry=False)
    client = (
        chromadb.PersistentClient(path=settings.chroma_path, settings=chroma_settings)
        if settings.chroma_path
        else chromadb.EphemeralClient(settings=chroma_settings)
    )
    collection = client.get_or_create_collection(
        COLLECTION, embedding_function=_embedding_function(), metadata={"hnsw:space": "cosine"}
    )
    if collection.count() == 0:
        docs = load_documents(settings.kb_path)
        embed = collection._embedding_function
        collection.add(
            ids=[d["id"] for d in docs],
            embeddings=embed([embedding_text(d) for d in docs]),
            documents=[d["content"] for d in docs],
            metadatas=[{"title": d["title"], "category": d["category"]} for d in docs],
        )
        log.info("kb.loaded", documents=len(docs))
    return collection


def search(query: str, category: str | None = None, k: int = 3) -> list[dict]:
    collection = get_collection()
    res = collection.query(
        query_texts=[query],
        n_results=k,
        where={"category": category} if category else None,
    )
    return [
        {
            "id": doc_id,
            "title": meta["title"],
            "category": meta["category"],
            "content": doc,
            "score": round(1 - dist, 3),
        }
        for doc_id, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]
