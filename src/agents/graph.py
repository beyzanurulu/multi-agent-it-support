"""LangGraph StateGraph wiring: supervisor hub with three specialised agents."""

from langgraph.graph import END, START, StateGraph

from src.agents.human_loop import human_approval_node
from src.agents.solution import solution_node
from src.agents.state import AgentState
from src.agents.supervisor import supervisor_node
from src.agents.ticket import ticket_node
from src.agents.triage import triage_node


def _next(state: AgentState) -> str:
    return state["next_agent"]


def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("triage", triage_node)
    graph.add_node("solution", solution_node)
    graph.add_node("ticket", ticket_node)
    graph.add_node("human_approval", human_approval_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _next,
        {
            "triage": "triage",
            "solution": "solution",
            "ticket": "ticket",
            "human_approval": "human_approval",
            "end": END,
        },
    )
    for agent in ("triage", "solution", "ticket", "human_approval"):
        graph.add_edge(agent, "supervisor")

    return graph.compile(checkpointer=checkpointer)
