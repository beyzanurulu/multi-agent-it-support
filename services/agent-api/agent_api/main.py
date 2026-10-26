"""agent-api: FastAPI gateway around the LangGraph multi-agent system."""

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from langgraph.store.memory import InMemoryStore
from prometheus_client import make_asgi_app
from pydantic import BaseModel, Field

from agent_api import runner
from agent_api.core.auth import (
    Principal,
    check_password,
    current_principal,
    issue_token,
    verify_token,
)
from agent_api.core.config import get_settings
from agent_api.core.logging import setup_logging, setup_tracing
from agent_api.graph.build import build_graph
from agent_api.memory.checkpointer import make_checkpointer, postgres_pool
from agent_api.memory.store import make_store

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    setup_tracing()
    async with postgres_pool(get_settings().database_url) as pool:
        app.state.pool = pool
        app.state.graph = build_graph(checkpointer=await make_checkpointer(pool),
                                      store=await make_store(pool))
        log.info("agent_api.ready")
        yield


app = FastAPI(title="Türkçe IT Destek — agent-api", version="0.2.0", lifespan=lifespan)
app.mount("/metrics", make_asgi_app())


class LoginRequest(BaseModel):
    user_id: str
    password: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class ResumeRequest(BaseModel):
    approved: bool


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login")
async def login(req: LoginRequest) -> dict:
    if not check_password(req.user_id, req.password):
        raise HTTPException(401, "kullanıcı adı veya şifre hatalı")
    async with app.state.pool.connection() as conn:
        user = await (await conn.execute(
            "SELECT u.id, u.role, d.name AS department FROM users u "
            "LEFT JOIN departments d ON d.id = u.department_id WHERE u.id = %s",
            (req.user_id,))).fetchone()
    if user is None:
        raise HTTPException(401, "kullanıcı bulunamadı")
    principal = Principal(user_id=user["id"], role=user["role"], department=user["department"])
    return {"token": issue_token(principal), **principal.model_dump()}


async def _collect(gen) -> dict:
    events, final = [], {}
    async for event in gen:
        if event["type"] == "done":
            final = event
        else:
            events.append(event)
    return {**final, "events": events,
            "messages": [e for e in events if e["type"] == "message"]}


@app.post("/chat")
async def chat(req: ChatRequest, principal: Principal = Depends(current_principal)) -> dict:
    session_id = req.session_id or str(uuid.uuid4())
    return await _collect(runner.stream_turn(app.state.graph, app.state.pool, principal,
                                             session_id, message=req.message))


@app.post("/chat/{session_id}/resume")
async def resume(session_id: str, req: ResumeRequest,
                 principal: Principal = Depends(current_principal)) -> dict:
    return await _collect(runner.stream_turn(app.state.graph, app.state.pool, principal,
                                             session_id, approved=req.approved))


@app.get("/chat/{session_id}")
async def session(session_id: str, principal: Principal = Depends(current_principal)) -> dict:
    return await runner.summary(app.state.graph, principal, session_id)


@app.websocket("/ws/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    try:
        principal = verify_token(websocket.query_params.get("token", ""))
    except HTTPException:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "approval":
                gen = runner.stream_turn(app.state.graph, app.state.pool, principal, session_id,
                                         approved=bool(data.get("approved")))
            else:
                gen = runner.stream_turn(app.state.graph, app.state.pool, principal, session_id,
                                         message=str(data.get("message", ""))[:4000])
            async for event in gen:
                await websocket.send_json(event, mode="text")
    except WebSocketDisconnect:
        pass


def build_inmemory_app() -> FastAPI:
    """Used by evals: same graph, in-memory checkpointer/store, no usage counters."""
    from langgraph.checkpoint.memory import MemorySaver

    app.state.graph = build_graph(checkpointer=MemorySaver(), store=InMemoryStore())
    app.state.pool = None
    return app
