"""NLU service: POST /nlu -> intents (multi-label) + Turkish NER entities."""

import os
import time
from pathlib import Path

import structlog
from fastapi import FastAPI
from prometheus_client import Histogram, make_asgi_app

from nlu_service import rules
from nlu_service.schemas import NLURequest, NLUResponse

log = structlog.get_logger()
MODEL_DIR = Path(os.getenv("NLU_MODEL_DIR", "models/nlu"))
LATENCY = Histogram("nlu_inference_seconds", "NLU inference latency", ["backend"],
                    buckets=(0.005, 0.01, 0.02, 0.04, 0.08, 0.16, 0.5))


def load_backend():
    if (MODEL_DIR / "model.onnx").exists():
        from nlu_service.model import OnnxNLU

        log.info("nlu.backend", backend="onnx", model_dir=str(MODEL_DIR))
        return "onnx", OnnxNLU(MODEL_DIR)
    log.warning("nlu.backend", backend="rules", reason="model.onnx not found")
    return "rules", rules


BACKEND_NAME, BACKEND = load_backend()
app = FastAPI(title="NLU Service", version="0.2.0")
app.mount("/metrics", make_asgi_app())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "backend": BACKEND_NAME}


@app.post("/nlu", response_model=NLUResponse)
def nlu(req: NLURequest) -> NLUResponse:
    start = time.perf_counter()
    result = BACKEND.analyze(req.text)
    elapsed = time.perf_counter() - start
    LATENCY.labels(BACKEND_NAME).observe(elapsed)
    return NLUResponse(**result, backend=BACKEND_NAME, latency_ms=round(elapsed * 1000, 2))
