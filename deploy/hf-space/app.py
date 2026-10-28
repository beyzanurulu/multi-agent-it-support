"""Hugging Face Space entry point (Gradio SDK, no Gradio used).

Clones the repo, installs its dependencies into a separate venv with uv (so they never clash
with the Space's own Gradio install) and runs deploy/hf-space/start.sh, which serves Chainlit
on port 7860.
"""

import os
import secrets
import subprocess
from pathlib import Path

REPO = os.environ.get("REPO", "https://github.com/beyzanurulu/multi-agent-it-support.git")
REF = os.environ.get("REF", "main")
APP = Path.home() / "it-support"

if not APP.exists():
    subprocess.run(["git", "clone", "--depth", "1", "--branch", REF, REPO, str(APP)], check=True)

env = dict(os.environ)
env.update(
    UV_PROJECT_ENVIRONMENT=str(APP / ".venv"),
    UV_PYTHON="3.12",
    FASTEMBED_CACHE_PATH=str(APP / ".fastembed"),
)
subprocess.run(
    ["uv", "sync", "--frozen", "--no-dev", "--extra", "agent", "--extra", "mcp", "--extra", "nlu",
     "--extra", "db", "--extra", "ui", "--extra", "embeddings"],
    cwd=APP, env=env, check=True,
)

env.update(
    PATH=f"{APP / '.venv' / 'bin'}:{env['PATH']}",
    PG_BIN="/usr/lib/postgresql/15/bin",
    DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/helpdesk",
    READONLY_DATABASE_URL="postgresql://helpdesk_readonly:readonly@127.0.0.1:5432/helpdesk",
    NLU_URL="http://127.0.0.1:8002",
    MCP_URL="http://127.0.0.1:8001/mcp",
    AGENT_API_URL="http://127.0.0.1:8000",
    NLU_MODEL_DIR=str(APP / "models" / "nlu"),
    DAILY_MESSAGE_LIMIT="500",
    PORT="7860",
    PYTHONUNBUFFERED="1",
)
env.setdefault("AUTH_SECRET", secrets.token_hex(24))
env.setdefault("CHAINLIT_AUTH_SECRET", secrets.token_hex(32))
os.chdir(APP)
os.execvpe("bash", ["bash", "deploy/hf-space/start.sh"], env)
