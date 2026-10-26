# Build from the repo root: docker build -f services/agent-api/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra agent
COPY services/agent-api ./services/agent-api
ENV PYTHONPATH=/app/services/agent-api
USER 1000
EXPOSE 8000
CMD ["uvicorn", "agent_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
