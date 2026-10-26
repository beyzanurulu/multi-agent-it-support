import os

os.environ.update({
    "NLU_URL": "inprocess", "MCP_URL": "inprocess", "OPENAI_API_KEY": "", "OLLAMA_URL": "",
    "EMBEDDING_PROVIDER": "hashing", "LANGSMITH_TRACING": "false",
})
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/helpdesk")
os.environ.setdefault(
    "READONLY_DATABASE_URL", "postgresql://helpdesk_readonly:readonly@localhost:5432/helpdesk")

import uuid

import pytest
from agent_api.graph.build import build_graph
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

ROLES = {"calisan": "employee", "uzman": "it_specialist", "yonetici": "manager"}


class Chat:
    """Drives one conversation thread against the compiled graph."""

    def __init__(self, app, user_id="calisan"):
        self.app, self.user_id = app, user_id
        self.config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 40}
        self.state = {}

    async def say(self, text):
        self.state = await self.app.ainvoke(
            {"messages": [HumanMessage(content=text)], "user_id": self.user_id,
             "role": ROLES[self.user_id], "department": None}, self.config)
        return self

    async def approve(self, approved=True):
        self.state = await self.app.ainvoke(Command(resume={"approved": approved}), self.config)
        return self

    @property
    def interrupt(self):
        return self.state["__interrupt__"][0].value if "__interrupt__" in self.state else None

    @property
    def last(self):
        return self.state["messages"][-1]

    def agents(self):
        return [getattr(m, "name", None) for m in self.state["messages"]]


@pytest.fixture
def app():
    return build_graph(checkpointer=MemorySaver(), store=InMemoryStore())


@pytest.fixture
def chat(app):
    return lambda user="calisan": Chat(app, user)
