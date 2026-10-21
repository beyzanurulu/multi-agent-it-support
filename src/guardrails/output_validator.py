"""Output validation with Guardrails AI + Pydantic.

- Solution text: must not leak secrets or recommend destructive commands.
- Ticket payload: schema-validated before it reaches the ticketing tool.
"""

import os
import re
from functools import lru_cache
from typing import Literal

from guardrails.validators import (
    FailResult,
    PassResult,
    ValidationResult,
    Validator,
    register_validator,
)
from pydantic import BaseModel, Field

# Validators are pure regex checks; run them synchronously even inside the event loop.
os.environ.setdefault("GUARDRAILS_RUN_SYNC", "true")

from guardrails import Guard

DESTRUCTIVE_PATTERNS = [
    r"rm\s+-rf",
    r"format\s+[a-z]:",
    r"del\s+/[sq]",
    r"reg\s+delete",
    r"diskpart",
    r"mkfs\.",
    r"drop\s+(table|database)",
]
SECRET_PATTERNS = [
    r"(şifre(niz)?|parola(nız)?|password)\s*[:=]\s*\S+",
    r"sk-[A-Za-z0-9]{20,}",
    r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",  # card-like numbers
]


@register_validator(name="it-support/no-destructive-commands", data_type="string")
class NoDestructiveCommands(Validator):
    def _validate(self, value: str, metadata: dict) -> ValidationResult:
        for pattern in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return FailResult(error_message=f"destructive command matched: {pattern}")
        return PassResult()


@register_validator(name="it-support/no-secrets", data_type="string")
class NoSecrets(Validator):
    def _validate(self, value: str, metadata: dict) -> ValidationResult:
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return FailResult(error_message="possible secret in output")
        return PassResult()


class TicketPayload(BaseModel):
    user_id: str = Field(min_length=1)
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    severity: Literal["low", "medium", "high", "critical"]
    category: str = Field(min_length=1)


@lru_cache
def _solution_guard() -> Guard:
    guard = Guard().use(NoDestructiveCommands(on_fail="noop"), NoSecrets(on_fail="noop"))
    guard.configure(allow_metrics_collection=False)
    return guard


@lru_cache
def _ticket_guard() -> Guard:
    guard = Guard.for_pydantic(TicketPayload)
    guard.configure(allow_metrics_collection=False)
    return guard


def validate_solution(text: str) -> tuple[bool, str | None]:
    if not 10 <= len(text) <= 3000:
        return False, "solution length out of bounds"
    outcome = _solution_guard().validate(text)
    if outcome.validation_passed:
        return True, None
    errors = [s.failure_reason for s in outcome.validation_summaries or [] if s.failure_reason]
    return False, "; ".join(errors) or "validation failed"


def validate_ticket(payload: dict) -> dict:
    """Return the validated payload or raise ValueError."""
    outcome = _ticket_guard().validate(TicketPayload.model_validate(payload).model_dump_json())
    if not outcome.validation_passed:
        raise ValueError(f"invalid ticket payload: {outcome.error}")
    return outcome.validated_output
