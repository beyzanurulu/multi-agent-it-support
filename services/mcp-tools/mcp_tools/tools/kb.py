"""Hybrid knowledge-base search: pgvector cosine + Postgres Turkish full-text, fused with RRF."""

from mcp_tools.db import get_pool
from mcp_tools.embeddings import get_embedder

RRF_K = 60

HYBRID_SQL = """
WITH vec AS (
    SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> %(emb)s::vector) AS rank
    FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id
    WHERE (%(category)s::text IS NULL OR d.category = %(category)s)
    ORDER BY c.embedding <=> %(emb)s::vector
    LIMIT 20
),
fts AS (
    SELECT c.id, row_number() OVER (
        ORDER BY ts_rank_cd(c.tsv, websearch_to_tsquery('turkish', %(q)s)) DESC) AS rank
    FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id
    WHERE c.tsv @@ websearch_to_tsquery('turkish', %(q)s)
      AND (%(category)s::text IS NULL OR d.category = %(category)s)
    LIMIT 20
),
codes AS (
    SELECT c.id, 1 AS rank
    FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id
    WHERE d.error_codes && %(codes)s::text[]
      AND (%(category)s::text IS NULL OR d.category = %(category)s)
),
fused AS (
    SELECT id, sum(1.0 / (%(k)s + rank)) AS score
    FROM (SELECT * FROM vec UNION ALL SELECT * FROM fts UNION ALL
          SELECT * FROM codes UNION ALL SELECT * FROM codes) s
    GROUP BY id
)
SELECT d.id AS doc_id, d.title, d.category, d.error_codes, c.content, f.score
FROM fused f
JOIN kb_chunks c ON c.id = f.id
JOIN kb_documents d ON d.id = c.doc_id
ORDER BY f.score DESC
"""


def _or_query(text: str) -> str:
    # websearch_to_tsquery ANDs terms; OR them so partial matches still rank.
    words = [w for w in text.replace('"', " ").split() if len(w) > 2]
    return " or ".join(words) or text


async def search_kb(
    query: str, category: str | None = None, error_codes: list[str] | None = None, k: int = 3
) -> list[dict]:
    """Hybrid search over the IT knowledge base. Returns the best chunk per document."""
    emb = get_embedder().embed([query])[0]
    params = {"emb": str(emb), "q": _or_query(query), "category": category,
              "codes": [c.upper() for c in error_codes or []], "k": RRF_K}
    async with get_pool().connection() as conn:
        rows = await (await conn.execute(HYBRID_SQL, params)).fetchall()
    results, seen = [], set()
    for row in rows:
        if row["doc_id"] in seen:
            continue
        seen.add(row["doc_id"])
        results.append({**row, "score": round(float(row["score"]), 4)})
        if len(results) == k:
            break
    if not results and category:
        return await search_kb(query, None, error_codes, k)
    return results
