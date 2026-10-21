"""Admin endpoints: tickets, pending approvals and per-session step traces."""

from fastapi import APIRouter, Depends, HTTPException

from src.api import runner
from src.api.deps import get_graph, require_api_key
from src.tools import crm

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_api_key)])


@router.get("/tickets")
async def list_tickets():
    return sorted(crm.TICKETS.values(), key=lambda t: t["created_at"], reverse=True)


@router.get("/notifications")
async def list_notifications():
    return crm.NOTIFICATIONS


@router.get("/sessions/{session_id}/trace")
async def session_trace(session_id: str, graph=Depends(get_graph)):
    """Checkpoint history: which agent ran at each step (complements LangSmith)."""
    steps = []
    async for snap in graph.aget_state_history(runner.config_for(session_id)):
        values = snap.values or {}
        steps.append({
            "checkpoint_id": snap.config["configurable"]["checkpoint_id"],
            "step": snap.metadata.get("step"),
            "agent": values.get("current_agent"),
            "next": list(snap.next),
            "iteration_count": values.get("iteration_count"),
            "created_at": snap.created_at,
        })
    if not steps:
        raise HTTPException(404, "session not found")
    return list(reversed(steps))
