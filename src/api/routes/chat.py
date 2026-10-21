"""Chat endpoints: REST turn-based chat, approvals and a streaming WebSocket."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src.api import runner
from src.api.deps import authorize_websocket, get_graph, rate_limiter, require_api_key

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = "anonymous"
    session_id: str | None = None


class ApprovalRequest(BaseModel):
    approved: bool
    note: str = ""


@router.post("/chat")
async def chat(req: ChatRequest, graph=Depends(get_graph), _=Depends(require_api_key)):
    session_id = req.session_id or str(uuid.uuid4())
    snap = await runner.snapshot(graph, session_id)
    if snap["pending_approval"]:
        raise HTTPException(409, "session is waiting for operator approval")
    return await runner.run_turn(graph, session_id, runner.turn_input(req.message, req.user_id))


@router.post("/chat/{session_id}/approval")
async def approve(
    session_id: str, req: ApprovalRequest, graph=Depends(get_graph), _=Depends(require_api_key)
):
    snap = await runner.snapshot(graph, session_id)
    if not snap["pending_approval"]:
        raise HTTPException(409, "no pending approval for this session")
    return await runner.run_turn(graph, session_id, runner.resume_input(req.approved, req.note))


@router.get("/chat/{session_id}")
async def get_session(session_id: str, graph=Depends(get_graph), _=Depends(require_api_key)):
    snap = await runner.snapshot(graph, session_id)
    if not snap["messages"]:
        raise HTTPException(404, "session not found")
    return snap


@router.websocket("/ws/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    try:
        client = authorize_websocket(websocket)
    except HTTPException:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    graph = websocket.app.state.graph
    try:
        while True:
            data = await websocket.receive_json()
            if not rate_limiter.check(f"ws:{client}:{session_id}"):
                await websocket.send_json({"type": "error", "detail": "rate limit exceeded"})
                continue
            if data.get("type") == "approval":
                payload = runner.resume_input(bool(data.get("approved")), data.get("note", ""))
            elif message := str(data.get("message", "")).strip():
                payload = runner.turn_input(message, data.get("user_id", "anonymous"))
            else:
                await websocket.send_json({"type": "error", "detail": "message is required"})
                continue
            async for event in runner.stream_turn(graph, session_id, payload):
                await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
