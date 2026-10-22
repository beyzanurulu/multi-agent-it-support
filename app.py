"""Single-process entrypoint for hosted demos (e.g. Hugging Face Spaces).

Serves the FastAPI gateway and the Gradio UI on one port; the UI talks to the
API over localhost.
"""

import os

PORT = int(os.getenv("PORT", "7860"))
os.environ.setdefault("API_KEYS", "demo-key")
os.environ.setdefault("DEMO_API_KEY", os.environ["API_KEYS"].split(",")[0])
os.environ.setdefault("API_URL", f"http://127.0.0.1:{PORT}")
os.environ.setdefault("CHECKPOINT_DB", "/tmp/checkpoints.sqlite")
# All UI traffic shares one key and host, so allow more than the per-client default.
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "300")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr
import uvicorn

from src.api.main import app as api
from src.ui.gradio_app import demo

app = gr.mount_gradio_app(api, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
