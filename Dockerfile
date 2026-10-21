FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False ANONYMIZED_TELEMETRY=False

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra demo --no-install-project

COPY src ./src
COPY data ./data
RUN uv sync --frozen --no-dev --extra demo

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000 7860
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
