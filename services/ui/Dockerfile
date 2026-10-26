# Build from the repo root: docker build -f services/ui/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra ui
COPY services/ui ./services/ui
WORKDIR /app/services/ui
RUN chown -R 1000 /app/services/ui
USER 1000
EXPOSE 8080
CMD ["chainlit", "run", "chainlit_app.py", "--headless", "--host", "0.0.0.0", "--port", "8080"]
