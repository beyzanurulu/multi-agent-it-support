"""Signed bearer tokens for the demo accounts (stdlib HMAC, no extra dependency)."""

import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from agent_api.core.config import get_settings

bearer = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    user_id: str
    role: str
    department: str | None = None


def _sign(payload: bytes) -> str:
    return hmac.new(get_settings().auth_secret.encode(), payload, hashlib.sha256).hexdigest()


def issue_token(principal: Principal) -> str:
    data = principal.model_dump() | {"exp": time.time() + get_settings().token_ttl_hours * 3600}
    payload = base64.urlsafe_b64encode(json.dumps(data).encode())
    return f"{payload.decode()}.{_sign(payload)}"


def verify_token(token: str) -> Principal:
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(payload.encode())):
            raise ValueError("bad signature")
        data = json.loads(base64.urlsafe_b64decode(payload))
        if data.pop("exp") < time.time():
            raise ValueError("expired")
        return Principal(**data)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc


def check_password(user_id: str, password: str) -> bool:
    accounts = dict(pair.split(":", 1) for pair in get_settings().demo_accounts.split(",") if pair)
    expected = accounts.get(user_id)
    return expected is not None and hmac.compare_digest(expected, password)


def current_principal(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing token")
    return verify_token(cred.credentials)
