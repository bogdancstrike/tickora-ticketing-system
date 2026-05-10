"""Distributor ticket review endpoint."""
from flask import request as flask_request
from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydValidationError

from src.config import Config
from src.common import rate_limiter
from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.serializers import serialize_ticket
from src.ticketing.service import review_service


class _ReviewTicketIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector_code: str | None = Field(default=None, max_length=50)
    assignee_user_id: str | None = None
    priority: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    type: str | None = Field(default=None, max_length=100)
    private_comment: str | None = Field(default=None, max_length=10000)
    reason: str | None = Field(default=None, max_length=1000)
    close: bool = False


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


def _ticket_id(kwargs: dict) -> str:
    tid = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    if not tid:
        raise ValidationError("ticket_id is required")
    return tid


@require_authenticated
def review_ticket(app, operation, request, *, principal: Principal, **kwargs):
    # Distributors do this constantly during peak triage, so the limit is
    # generous; the goal here is to defend against runaway scripts, not slow
    # down a real reviewer.
    rate_limiter.check(
        bucket="ticket_review",
        identity=principal.user_id or "anon",
        limit=Config.RATE_LIMIT_TICKET_REVIEW_PER_MIN,
        window_s=60,
    )
    try:
        body = _ReviewTicketIn(**_payload())
    except PydValidationError as e:
        raise ValidationError("invalid payload", details={"errors": e.errors()})

    with get_db() as db:
        ticket = review_service.review(
            db,
            principal,
            _ticket_id(kwargs),
            body.model_dump(exclude_unset=True),
        )
        return (serialize_ticket(ticket, principal), 200)
