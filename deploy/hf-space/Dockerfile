# Hugging Face Space (Docker SDK): the whole stack in one container, UI on port 7860.
# The Space repository only holds this file and README.md; the code is cloned from GitHub.
# Rebuild the Space (Settings -> Factory rebuild) to pick up new commits.
FROM python:3.12-slim-bookworm

ARG REPO=https://github.com/beyzanurulu/multi-agent-it-support.git
ARG REF=main

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg git \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update && apt-get install -y --no-install-recommends postgresql-16 postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*

COPY --from=astral/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/app/.fastembed

RUN git clone --depth 1 --branch "$REF" "$REPO" /app
WORKDIR /app
RUN uv sync --frozen --no-dev --extra agent --extra mcp --extra nlu --extra db --extra ui \
      --extra embeddings
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

ENV DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/helpdesk \
    READONLY_DATABASE_URL=postgresql://helpdesk_readonly:readonly@127.0.0.1:5432/helpdesk \
    NLU_URL=http://127.0.0.1:8002 \
    MCP_URL=http://127.0.0.1:8001/mcp \
    AGENT_API_URL=http://127.0.0.1:8000 \
    NLU_MODEL_DIR=/app/models/nlu \
    DAILY_MESSAGE_LIMIT=500 \
    PORT=7860

# Spaces run the container as uid 1000; initdb needs a passwd entry for it.
RUN useradd -m -u 1000 user && chmod +x deploy/hf-space/start.sh && chown -R user /app
USER 1000
EXPOSE 7860
CMD ["bash", "-c", "export AUTH_SECRET=${AUTH_SECRET:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \\n')} CHAINLIT_AUTH_SECRET=${CHAINLIT_AUTH_SECRET:-$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \\n')}; exec deploy/hf-space/start.sh"]
