"""Shared FastAPI dependencies: graph access, API-key auth, rate limiting."""

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import APIKeyHeader

from src.core.config import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class RateLimiter:
    """Sliding one-minute window per client key (single-process, in-memory)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        limit = get_settings().rate_limit_per_minute
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = RateLimiter()


def _authorize(key: str | None) -> str:
    allowed = get_settings().api_key_set
    if allowed and key not in allowed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")
    return key or "anonymous"


def require_api_key(request: Request, key: str | None = Depends(api_key_header)) -> str:
    client = _authorize(key)
    if not rate_limiter.check(f"{client}:{request.client.host if request.client else ''}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")
    return client


def authorize_websocket(websocket: WebSocket) -> str:
    key = websocket.headers.get("x-api-key") or websocket.query_params.get("api_key")
    return _authorize(key)


def get_graph(request: Request):
    return request.app.state.graph
