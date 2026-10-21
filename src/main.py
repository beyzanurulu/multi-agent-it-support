"""Minimal CLI to chat with the graph (the API lives in src/api)."""

import asyncio
import uuid

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.agents.graph import build_graph
from src.core.langsmith import setup_tracing
from src.memory.checkpointer import sqlite_checkpointer


async def main() -> None:
    setup_tracing()
    async with sqlite_checkpointer() as saver:
        app = build_graph(checkpointer=saver)
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        print("IT Destek — çıkmak için 'q'")
        while (text := input("> ").strip()) not in ("q", "quit"):
            seen = len((await app.aget_state(config)).values.get("messages", []))
            payload = {"messages": [HumanMessage(content=text)], "user_id": "u001",
                       "iteration_count": 0}
            state = await app.ainvoke(payload, config)
            while "__interrupt__" in state:
                question = state["__interrupt__"][0].value["question"]
                approved = input(f"[operatör] {question} (e/h) ").strip().lower() == "e"
                state = await app.ainvoke(Command(resume={"approved": approved}), config)
            for msg in state["messages"][seen + 1:]:
                print(f"[{msg.name}] {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())
