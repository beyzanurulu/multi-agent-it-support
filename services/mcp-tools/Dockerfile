# Build from the repo root: docker build -f services/mcp-tools/Dockerfile .
# Also used as the migration/seed job image (alembic + seed script are included).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/app/.fastembed
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra mcp --extra embeddings --extra db
# Bake the multilingual embedding model into the image (no download at runtime).
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
COPY services/mcp-tools ./services/mcp-tools
COPY db ./db
ENV PYTHONPATH=/app/services/mcp-tools
RUN chown -R 1000 /app/.fastembed
USER 1000
EXPOSE 8001
CMD ["python", "-m", "mcp_tools.server"]
