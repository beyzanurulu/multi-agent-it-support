# Build from the repo root: docker build -f services/nlu-service/Dockerfile .
FROM python:3.12-slim
COPY --from=astral/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra nlu
COPY services/nlu-service ./services/nlu-service
# Exported BERTurk model (optional; without it the rule-based backend is used).
COPY models/nlu ./models/nlu
ENV PYTHONPATH=/app/services/nlu-service NLU_MODEL_DIR=/app/models/nlu
USER 1000
EXPOSE 8002
CMD ["uvicorn", "nlu_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
