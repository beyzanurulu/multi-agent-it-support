"""Minimal CLI to chat with the graph until the API layer lands (Week 4)."""

import uuid

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.graph import build_graph
from src.core.langsmith import setup_tracing


def main() -> None:
    setup_tracing()
    app = build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    print("IT Destek — çıkmak için 'q'")
    while (text := input("> ").strip()) not in ("q", "quit"):
        seen = len(app.get_state(config).values.get("messages", []))
        state = app.invoke(
            {"messages": [HumanMessage(content=text)], "user_id": "cli-user", "iteration_count": 0},
            config,
        )
        for msg in state["messages"][seen + 1:]:
            print(f"[{msg.name}] {msg.content}")


if __name__ == "__main__":
    main()
