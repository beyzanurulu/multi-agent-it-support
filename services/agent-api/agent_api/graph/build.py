"""Graph assembly. Agents route with Command(goto=...), so only entry edges are declared."""

from langgraph.graph import START, StateGraph

from agent_api.graph.analytics import analytics
from agent_api.graph.solution import solution
from agent_api.graph.state import AgentState
from agent_api.graph.supervisor import guard_in, nlu_node, supervisor
from agent_api.graph.ticket import ticket
from agent_api.graph.triage import triage


def build_graph(checkpointer=None, store=None):
    g = StateGraph(AgentState)
    g.add_node("guard_in", guard_in, destinations=("nlu", "__end__"))
    g.add_node("nlu", nlu_node)
    g.add_node("supervisor", supervisor,
               destinations=("triage", "solution", "ticket", "analytics", "supervisor", "__end__"))
    g.add_node("triage", triage, destinations=("supervisor",))
    g.add_node("solution", solution, destinations=("supervisor",))
    g.add_node("ticket", ticket, destinations=("supervisor",))
    g.add_node("analytics", analytics, destinations=("supervisor",))
    g.add_edge(START, "guard_in")
    g.add_edge("nlu", "supervisor")
    return g.compile(checkpointer=checkpointer, store=store)
