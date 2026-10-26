from pydantic import BaseModel, Field


class NLURequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class IntentScore(BaseModel):
    label: str
    score: float


class Entity(BaseModel):
    label: str
    text: str
    start: int
    end: int


class NLUResponse(BaseModel):
    intents: list[IntentScore]
    entities: list[Entity]
    backend: str
    latency_ms: float
