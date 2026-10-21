"""Infinite-loop protection for the agent graph."""

from src.agents.state import AgentState
from src.core.config import get_settings


def limit_reached(state: AgentState) -> bool:
    return state.get("iteration_count", 0) >= get_settings().max_iterations
