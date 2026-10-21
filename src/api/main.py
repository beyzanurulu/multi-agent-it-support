"""FastAPI gateway."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.agents.graph import build_graph
from src.api.routes import admin, chat
from src.core.langsmith import setup_tracing
from src.memory.checkpointer import sqlite_checkpointer
from src.memory.kb_loader import get_collection

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_tracing()
    get_collection()  # warm up the knowledge base
    async with sqlite_checkpointer() as saver:
        app.state.graph = build_graph(checkpointer=saver)
        log.info("api.ready")
        yield


app = FastAPI(title="Multi-Agent IT Support", version="0.1.0", lifespan=lifespan)
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
