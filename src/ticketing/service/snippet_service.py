"""Snippets — admin-authored procedures with audience scoping.

Visibility model:
    A snippet is visible to a principal when EITHER
      * it has zero audience rows (public to every signed-in user), OR
      * at least one audience row matches the principal's
        sectors / realm roles / beneficiary type.

Writes (create / update / delete) are admin-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.common.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.iam.principal import Principal
from src.audit import events
from src.audit import service as audit_service
from src.ticketing.models import Snippet, SnippetAudience

VALID_KINDS = {"sector", "role", "beneficiary_type"}


def _require_admin(principal: Principal) -> None:
    if not (principal.is_admin or principal.has_root_group):
        raise PermissionDeniedError("admin only")


# ── Reads ────────────────────────────────────────────────────────────────────

def list_(db: Session, principal: Principal) -> list[Snippet]:
    """Return every snippet the principal is allowed to see, ordered by title."""
    stmt = (
        select(Snippet)
        .options(selectinload(Snippet.audiences))
        .order_by(Snippet.title.asc())
    )
    snippets = list(db.scalars(stmt))
    return [s for s in snippets if _is_visible(s, principal)]


def get(db: Session, principal: Principal, snippet_id: str) -> Snippet:
    row = db.get(Snippet, snippet_id, options=[selectinload(Snippet.audiences)])
    if row is None:
        raise NotFoundError("snippet not found")
    if not _is_visible(row, principal):
        # Hide existence from non-audience principals — same pattern as
        # tickets: avoid leaking via 403/404 distinction.
        raise NotFoundError("snippet not found")
    return row


def _is_visible(snippet: Snippet, principal: Principal) -> bool:
    if principal.is_admin or principal.has_root_group:
        return True
    rows = snippet.audiences or []
    if not rows:
        return True  # public snippet
    for r in rows:
        if r.audience_kind == "sector" and r.audience_value in principal.all_sectors:
            return True
        if r.audience_kind == "role" and r.audience_value in principal.global_roles:
            return True
        if r.audience_kind == "beneficiary_type" and r.audience_value == principal.user_type:
            return True
    return False


# ── Writes (admin) ──────────────────────────────────────────────────────────

def create(db: Session, principal: Principal, payload: dict[str, Any]) -> Snippet:
    _require_admin(principal)
    title = (payload.get("title") or "").strip()
    body  = (payload.get("body")  or "").strip()
    if not title:
        raise ValidationError("title is required")
    if not body:
        raise ValidationError("body is required")
    row = Snippet(
        title=title[:255],
        body=body,
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    db.flush()
    _replace_audiences(db, row, payload.get("audiences") or [])
    db.flush()
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="snippet", entity_id=row.id,
        new_value={"title": row.title, "audiences": _audience_payload(row.audiences)},
        metadata={"action": "create"},
    )
    return row


def update(db: Session, principal: Principal, snippet_id: str, payload: dict[str, Any]) -> Snippet:
    _require_admin(principal)
    row = db.get(Snippet, snippet_id, options=[selectinload(Snippet.audiences)])
    if row is None:
        raise NotFoundError("snippet not found")
    if "title" in payload:
        title = (payload["title"] or "").strip()
        if not title:
            raise ValidationError("title cannot be empty")
        row.title = title[:255]
    if "body" in payload:
        body = (payload["body"] or "").strip()
        if not body:
            raise ValidationError("body cannot be empty")
        row.body = body
    if "audiences" in payload:
        _replace_audiences(db, row, payload["audiences"] or [])
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="snippet", entity_id=row.id,
        new_value={"title": row.title, "audiences": _audience_payload(row.audiences)},
        metadata={"action": "update"},
    )
    return row


def delete(db: Session, principal: Principal, snippet_id: str) -> None:
    _require_admin(principal)
    row = db.get(Snippet, snippet_id)
    if row is None:
        raise NotFoundError("snippet not found")
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="snippet", entity_id=snippet_id,
        old_value={"title": row.title},
        metadata={"action": "delete"},
    )
    db.delete(row)


def _replace_audiences(db: Session, row: Snippet, audiences: list[dict[str, str]]) -> None:
    """Drop the existing audience set and replace it with the payload's.
    The list comes in as `[{kind, value}, …]`; an empty list means
    "public" (everyone can see)."""
    # Cascade='all, delete-orphan' on the relationship handles deletes
    # when we replace the collection.
    new_rows: list[SnippetAudience] = []
    seen: set[tuple[str, str]] = set()
    for a in audiences:
        kind  = (a.get("kind")  or a.get("audience_kind")  or "").strip()
        value = (a.get("value") or a.get("audience_value") or "").strip()
        if not kind or not value:
            raise ValidationError("each audience needs both `kind` and `value`")
        if kind not in VALID_KINDS:
            raise ValidationError(f"invalid audience kind: {kind!r}")
        key = (kind, value)
        if key in seen:
            continue
        seen.add(key)
        new_rows.append(SnippetAudience(
            snippet_id=row.id, audience_kind=kind, audience_value=value,
        ))
    row.audiences = new_rows


def _audience_payload(rows: list[SnippetAudience] | None) -> list[dict[str, str]]:
    return [
        {"kind": r.audience_kind, "value": r.audience_value}
        for r in (rows or [])
    ]


def serialize(s: Snippet) -> dict[str, Any]:
    return {
        "id":                 s.id,
        "title":               s.title,
        "body":                s.body,
        "created_by_user_id":  s.created_by_user_id,
        "audiences":           _audience_payload(s.audiences),
        "created_at":          s.created_at.isoformat() if s.created_at else None,
        "updated_at":          s.updated_at.isoformat() if s.updated_at else None,
    }
