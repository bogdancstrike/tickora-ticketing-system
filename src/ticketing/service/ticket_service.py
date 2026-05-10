"""Ticket service — create/list/get with RBAC-baked visibility."""
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import and_, asc, desc, exists, func, or_, select
from sqlalchemy.orm import Session

from src.common.correlation import get_correlation_id, set_ticket_id
from src.common.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.common.pagination import Cursor, clamp_limit
from src.common.spans import set_attr, span
from src.iam.principal import Principal
from src.iam import rbac
from src.iam.models import User
from src.audit import events
from src.ticketing.models import (
    Beneficiary, Sector, Ticket, TicketAssignee, TicketSectorAssignment,
)
from src.audit import service as audit_service
from src.ticketing.service import beneficiary_service, sla_service
from src.tasking.producer import publish


# ── Ticket code generation ───────────────────────────────────────────────────

def _generate_ticket_code(db: Session) -> str:
    """Format `TK-YYYY-NNNNNN` using a year-scoped Postgres sequence.

    The sequence is created lazily; reads from `pg_class` to avoid the cost of
    `CREATE SEQUENCE IF NOT EXISTS` (which is dialect-specific phrasing).
    """
    year = datetime.now(timezone.utc).year
    seq = f"ticket_code_{year}"
    db.execute(_sequence_create_sql(seq))
    nextval = db.execute(_nextval_sql(seq)).scalar_one()
    return f"TK-{year}-{int(nextval):06d}"


def _sequence_create_sql(name: str):
    from sqlalchemy import text
    return text(f"CREATE SEQUENCE IF NOT EXISTS {name} START 1 INCREMENT 1")


def _nextval_sql(name: str):
    from sqlalchemy import text
    return text(f"SELECT nextval('{name}')")


# ── Visibility predicate ─────────────────────────────────────────────────────

def _visibility_filter(p: Principal):
    """SQLAlchemy filter expression encoding `rbac.can_view_ticket` for a query.

    Returns ``None`` for principals with unrestricted read scope (admin /
    auditor) so the caller can skip adding a WHERE clause altogether — the
    planner picks shorter paths when no visibility predicate is in the way.

    For everyone else we OR together every legitimate path to a ticket:
    creator, beneficiary by user_id, external requester by email, sector
    membership (both `current_sector_id` and the multi-sector
    `ticket_sectors` join), and the distributor's pending/triage queue. The
    OR is built from a list of clauses so the SQL planner can pick the
    cheapest branch (for example, an indexed equality on
    ``created_by_user_id`` for "My tickets").

    Bandwidth: this filter is used by the list endpoint **and** by every
    aggregate in `monitor_service`, so any change here ripples wide. Keep it
    in lock-step with `iam.rbac.can_view_ticket` — the python and SQL
    versions are tested as a pair.
    """
    if p.is_admin or p.is_auditor:
        return None  # no restriction

    clauses = []
    # creator
    clauses.append(Ticket.created_by_user_id == p.user_id)
    # beneficiary linked to the user
    clauses.append(
        Ticket.beneficiary_id.in_(
            select(Beneficiary.id).where(Beneficiary.user_id == p.user_id)
        )
    )
    # external beneficiary/requester matched by authenticated email
    if p.email:
        clauses.append(
            and_(
                Ticket.beneficiary_type == "external",
                Ticket.requester_email == p.email,
            )
        )
    # sector membership (any sector_code in p.all_sectors)
    if p.all_sectors:
        clauses.append(
            Ticket.current_sector_id.in_(
                select(Sector.id).where(Sector.code.in_(p.all_sectors))
            )
        )
        clauses.append(
            exists(
                select(1)
                .select_from(TicketSectorAssignment)
                .join(Sector, Sector.id == TicketSectorAssignment.sector_id)
                .where(
                    TicketSectorAssignment.ticket_id == Ticket.id,
                    Sector.code.in_(p.all_sectors),
                )
            )
        )
    # distributor sees pending/assigned_to_sector
    if p.is_distributor:
        clauses.append(Ticket.status.in_(("pending", "assigned_to_sector")))
    return or_(*clauses)


# ── Public API ───────────────────────────────────────────────────────────────

def create(db: Session, principal: Principal, payload: dict[str, Any]) -> Ticket:
    """Creates a new ticket, generating a code and recording the creation event.

    Args:
        db: Database session.
        principal: The authenticated user creating the ticket.
        payload: Dictionary containing ticket details (title, txt, beneficiary_type, etc.).

    Returns:
        The newly created Ticket object.
    """
    with span("ticket.create", username=principal.username, user_id=principal.user_id) as current:
        btype = payload.get("beneficiary_type")
        set_attr(current, "ticket.beneficiary_type", btype)
        ticket = _create(db, principal, payload)
        set_attr(current, "ticket.id", ticket.id)
        set_attr(current, "ticket.code", ticket.ticket_code)
        set_attr(current, "ticket.priority", ticket.priority)
        return ticket


def _create(db: Session, principal: Principal, payload: dict[str, Any]) -> Ticket:
    btype = payload.get("beneficiary_type")
    if btype not in ("internal", "external"):
        raise ValidationError("beneficiary_type must be 'internal' or 'external'")

    txt = (payload.get("txt") or "").strip()
    if len(txt) < 5:
        raise ValidationError("txt must be at least 5 characters")
    if len(txt) > 20000:
        raise ValidationError("txt too long")

    # Beneficiary
    if btype == "internal":
        beneficiary = beneficiary_service.get_or_create_internal(db, principal)
    else:
        beneficiary = beneficiary_service.create_external(db, payload)

    # Capture request metadata
    source_ip, user_agent = _request_metadata()

    code = _generate_ticket_code(db)
    ticket = Ticket(
        ticket_code      = code,
        beneficiary_id   = beneficiary.id,
        beneficiary_type = btype,
        created_by_user_id = principal.user_id if btype == "internal" else None,

        requester_first_name   = payload.get("requester_first_name") or beneficiary.first_name,
        requester_last_name    = payload.get("requester_last_name")  or beneficiary.last_name,
        requester_email        = payload.get("requester_email")      or beneficiary.email,
        requester_phone        = payload.get("requester_phone")      or beneficiary.phone,
        requester_organization = payload.get("organization_name")    or beneficiary.organization_name,

        requester_ip   = payload.get("requester_ip"),
        source_ip      = source_ip,
        user_agent     = user_agent,
        correlation_id = get_correlation_id(),

        suggested_sector_id = None,

        title      = (payload.get("title") or txt[:120]).strip()[:500],
        txt        = txt,
        category   = None,
        type       = None,
        priority   = "medium",
        status     = "pending",
    )
    sla_service.evaluate_sla(db, ticket)
    db.add(ticket)
    db.flush()
    set_ticket_id(ticket.id)

    audit_service.record(
        db,
        actor       = principal,
        action      = events.TICKET_CREATED,
        entity_type = "ticket",
        entity_id   = ticket.id,
        ticket_id   = ticket.id,
        new_value   = _ticket_audit_snapshot(ticket),
        metadata    = {"source": "api"},
    )

    publish("notify_distributors", {"ticket_id": ticket.id})

    return ticket


def get(db: Session, principal: Principal, ticket_id: str) -> Ticket:
    """Retrieves a single ticket by ID, performing RBAC visibility checks.

    Args:
        db: Database session.
        principal: The authenticated user requesting the ticket.
        ticket_id: The UUID string of the ticket.

    Returns:
        The hydrated Ticket object.

    Raises:
        NotFoundError: If the ticket doesn't exist or is not visible to the user.
    """
    with span("ticket.get", username=principal.username, user_id=principal.user_id, ticket_id=ticket_id) as current:
        t = db.get(Ticket, ticket_id)
        if t is None or t.is_deleted:
            set_attr(current, "ticket.found", False)
            raise NotFoundError("ticket not found")
        setattr(t, "current_sector_code", _sector_code(db, t.current_sector_id))
        setattr(t, "beneficiary_user_id", _beneficiary_user_id(db, t.beneficiary_id))
        setattr(t, "sector_codes", _sector_codes_for_ticket(db, t.id))
        setattr(t, "assignee_users", _assignees_for_ticket(db, t.id))
        _hydrate_requester_fallback(db, t)
        set_attr(current, "ticket.found", True)
        set_attr(current, "ticket.code", t.ticket_code)
        set_attr(current, "ticket.status", t.status)

        if not rbac.can_view_ticket(principal, t):
            set_attr(current, "ticket.visible", False)
            raise NotFoundError("ticket not found")
        set_attr(current, "ticket.visible", True)
        set_ticket_id(t.id)
        return t


def update(db: Session, principal: Principal, ticket_id: str, payload: dict[str, Any]) -> Ticket:
    """Updates ticket title and description, recording an audit event.

    Args:
        db: Database session.
        principal: The authenticated user performing the update.
        ticket_id: The UUID string of the ticket.
        payload: Dictionary containing fields to update.

    Returns:
        The updated Ticket object.

    Raises:
        PermissionDeniedError: If the user doesn't have update permissions.
    """
    with span("ticket.update", username=principal.username, user_id=principal.user_id, ticket_id=ticket_id) as current:
        t = get(db, principal, ticket_id)
        if not rbac.can_update_ticket(principal, t):
            raise PermissionDeniedError("not allowed to update this ticket")

        old_val = _ticket_audit_snapshot(t)
        
        if "title" in payload:
            t.title = (payload["title"] or "").strip()[:500]
        if "txt" in payload:
            t.txt = (payload["txt"] or "").strip()
            
        db.flush()
        new_val = _ticket_audit_snapshot(t)
        
        if old_val != new_val:
            audit_service.record(
                db,
                actor=principal,
                action=events.TICKET_UPDATED,
                entity_type="ticket",
                entity_id=t.id,
                ticket_id=t.id,
                old_value=old_val,
                new_value=new_val,
            )
        
        return t


def delete(db: Session, principal: Principal, ticket_id: str) -> None:
    with span("ticket.delete", username=principal.username, user_id=principal.user_id, ticket_id=ticket_id):
        t = get(db, principal, ticket_id)
        if not rbac.can_delete_ticket(principal, t):
            raise PermissionDeniedError("not allowed to delete this ticket")

        t.is_deleted = True
        db.flush()
        
        audit_service.record(
            db,
            actor=principal,
            action=events.TICKET_DELETED,
            entity_type="ticket",
            entity_id=t.id,
            ticket_id=t.id,
            old_value={"is_deleted": False},
            new_value={"is_deleted": True},
        )


def list_(
    db: Session,
    principal: Principal,
    *,
    filters: dict[str, Any] | None = None,
    cursor_token: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[list[Ticket], str | None, int]:
    """Lists tickets visible to the principal, supporting filtering and pagination.

    Args:
        db: Database session.
        principal: The authenticated user listing tickets.
        filters: Optional filters (status, priority, sector, search, etc.).
        cursor_token: Optional token for cursor-based pagination (created_at desc).
        limit: Max number of items to return.
        offset: Optional offset for page-based pagination.

    Returns:
        A tuple of (list of tickets, next_cursor_token, total_count).
    """
    with span("ticket.list", username=principal.username, user_id=principal.user_id) as current:
        rows, next_token, total = _list(db, principal, filters=filters, cursor_token=cursor_token, limit=limit, offset=offset)
        set_attr(current, "ticket.count", len(rows))
        set_attr(current, "ticket.total", total)
        set_attr(current, "pagination.has_next", bool(next_token))
        return rows, next_token, total


def _list(
    db: Session,
    principal: Principal,
    *,
    filters: dict[str, Any] | None = None,
    cursor_token: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[list[Ticket], str | None, int]:
    filters = filters or {}
    limit = clamp_limit(limit, default=50, max_=200)

    stmt = select(Ticket).where(Ticket.is_deleted.is_(False))

    vis = _visibility_filter(principal)
    if vis is not None:
        stmt = stmt.where(vis)

    # ── Filters ────────────────────────────────────────────────────────────
    if (status := filters.get("status")):
        statuses = status if isinstance(status, list) else [status]
        stmt = stmt.where(Ticket.status.in_(statuses))
    if (priority := filters.get("priority")):
        priorities = priority if isinstance(priority, list) else [priority]
        stmt = stmt.where(Ticket.priority.in_(priorities))
    if (category := filters.get("category")):
        stmt = stmt.where(Ticket.category == category)
    if (btype := filters.get("beneficiary_type")):
        stmt = stmt.where(Ticket.beneficiary_type == btype)
    if (assignee := filters.get("assignee_user_id")):
        stmt = stmt.where(
            or_(
                Ticket.assignee_user_id == assignee,
                exists(
                    select(1)
                    .select_from(TicketAssignee)
                    .where(
                        TicketAssignee.ticket_id == Ticket.id,
                        TicketAssignee.user_id == assignee,
                    )
                ),
            )
        )
    if (sector_code := filters.get("current_sector_code")):
        stmt = stmt.where(
            or_(
                Ticket.current_sector_id.in_(
                    select(Sector.id).where(Sector.code == sector_code)
                ),
                exists(
                    select(1)
                    .select_from(TicketSectorAssignment)
                    .join(Sector, Sector.id == TicketSectorAssignment.sector_id)
                    .where(
                        TicketSectorAssignment.ticket_id == Ticket.id,
                        Sector.code == sector_code,
                    )
                ),
            )
        )
    if (created_after := filters.get("created_after")):
        stmt = stmt.where(Ticket.created_at >= created_after)
    if (created_before := filters.get("created_before")):
        stmt = stmt.where(Ticket.created_at < created_before)
    if (code := filters.get("ticket_code")):
        stmt = stmt.where(Ticket.ticket_code == code)
    if (search := filters.get("search")):
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Ticket.title.ilike(like),
                Ticket.txt.ilike(like),
                Ticket.ticket_code.ilike(like),
            )
        )

    # ── Count ─────────────────────────────────────────────────────────────
    # Counting a visibility-filtered subquery on a multi-million-row table is
    # the dominant cost on this endpoint. We accept a small inaccuracy on huge
    # admin-scope sets in exchange for a hard cap on latency:
    #   * If the user is admin/auditor and no narrowing filter is applied, use
    #     `pg_class.reltuples` (kept fresh by autovacuum/ANALYZE).
    #   * Otherwise run the real COUNT — the visibility predicate or an
    #     explicit filter shrinks the set enough that COUNT is acceptable.
    has_narrowing_filter = any(
        filters.get(k)
        for k in (
            "status", "priority", "category", "beneficiary_type",
            "assignee_user_id", "current_sector_code", "ticket_code",
            "search", "created_after", "created_before",
        )
    )
    if (principal.is_admin or principal.is_auditor) and not has_narrowing_filter:
        from sqlalchemy import text
        approx = db.scalar(
            text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'tickets'")
        )
        total_count = int(approx or 0)
    else:
        total_count = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)

    # ── Sort + cursor (cursor only supported on created_at-desc) ───────────
    sort_by = (filters.get("sort_by") or "created_at")
    sort_dir = (filters.get("sort_dir") or "desc").lower()
    sort_col = {
        "created_at":  Ticket.created_at,
        "updated_at":  Ticket.updated_at,
        "ticket_code": Ticket.ticket_code,
        "priority":    Ticket.priority,
        "status":      Ticket.status,
        "title":       Ticket.title,
    }.get(sort_by, Ticket.created_at)
    direction = desc if sort_dir == "desc" else asc

    cursor = Cursor.decode(cursor_token) if (sort_by == "created_at" and sort_dir == "desc") else None
    if cursor is not None:
        stmt = stmt.where(
            or_(
                Ticket.created_at < cursor.sort_value,
                and_(Ticket.created_at == cursor.sort_value, Ticket.id < cursor.id),
            )
        )
    
    stmt = stmt.order_by(direction(sort_col), direction(Ticket.id))
    
    if offset is not None:
        stmt = stmt.offset(offset)
        
    stmt = stmt.limit(limit + 1)

    rows = list(db.scalars(stmt))
    next_token: str | None = None
    if len(rows) > limit:
        nxt = rows[limit - 1]
        # Cursor is only emitted for the default sort (created_at desc)
        if sort_by == "created_at" and sort_dir == "desc":
            next_token = Cursor(sort_value=nxt.created_at, id=nxt.id).encode()
        rows = rows[:limit]

    # Hydrate sector_code / beneficiary_user_id for downstream RBAC/serializer.
    sector_codes = _sector_codes_map(db, [r.current_sector_id for r in rows if r.current_sector_id])
    ben_user_ids = _beneficiary_user_ids_map(db, [r.beneficiary_id for r in rows if r.beneficiary_id])
    multi_sectors = _sector_codes_per_ticket(db, [r.id for r in rows])
    multi_assignees = _assignees_per_ticket(db, [r.id for r in rows])
    for r in rows:
        setattr(r, "current_sector_code", sector_codes.get(r.current_sector_id))
        setattr(r, "beneficiary_user_id", ben_user_ids.get(r.beneficiary_id))
        setattr(r, "sector_codes", multi_sectors.get(r.id, []))
        setattr(r, "assignee_users", multi_assignees.get(r.id, []))
    return rows, next_token, total_count


# ── Helpers ──────────────────────────────────────────────────────────────────

def _request_metadata() -> tuple[str | None, str | None]:
    # Single source of truth for "what's the client IP?" — trusted-proxy
    # aware so a direct caller cannot forge `X-Forwarded-For`.
    from src.common.request_metadata import request_metadata
    return request_metadata()


def _ticket_audit_snapshot(t: Ticket) -> dict[str, Any]:
    return {
        "id":                  t.id,
        "ticket_code":         t.ticket_code,
        "status":              t.status,
        "priority":            t.priority,
        "category":            t.category,
        "type":                t.type,
        "beneficiary_type":    t.beneficiary_type,
        "current_sector_id":   t.current_sector_id,
        "suggested_sector_id": t.suggested_sector_id,
        "assignee_user_id":    t.assignee_user_id,
        "created_by_user_id":  t.created_by_user_id,
        "title":               t.title,
    }


def _sector_code(db: Session, sector_id: str | None) -> str | None:
    if not sector_id:
        return None
    return db.scalar(select(Sector.code).where(Sector.id == sector_id))


def _sector_codes_map(db: Session, ids: Iterable[str]) -> dict[str, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = db.execute(select(Sector.id, Sector.code).where(Sector.id.in_(ids))).all()
    return {sid: code for sid, code in rows}


def _beneficiary_user_id(db: Session, beneficiary_id: str | None) -> str | None:
    if not beneficiary_id:
        return None
    return db.scalar(select(Beneficiary.user_id).where(Beneficiary.id == beneficiary_id))


def _hydrate_requester_fallback(db: Session, t: Ticket) -> None:
    """Populate transient `_requester_*_fallback` attrs from the beneficiary
    (and, for internal types, the linked user) so the serializer can fill
    blanks left over from older tickets without writing back to the DB."""
    needs = (
        not t.requester_first_name
        or not t.requester_last_name
        or not t.requester_email
        or not t.requester_phone
        or not t.requester_organization
    )
    if not needs or not t.beneficiary_id:
        return
    ben = db.get(Beneficiary, t.beneficiary_id)
    if ben is None:
        return
    first = ben.first_name
    last = ben.last_name
    email = ben.email
    phone = ben.phone
    if ben.beneficiary_type == "internal" and ben.user_id and not (first and last and email):
        from src.iam.models import User
        user = db.get(User, ben.user_id)
        if user is not None:
            first = first or user.first_name
            last = last or user.last_name
            email = email or user.email
    setattr(t, "_requester_first_name_fallback", first)
    setattr(t, "_requester_last_name_fallback", last)
    setattr(t, "_requester_email_fallback", email)
    setattr(t, "_requester_phone_fallback", phone)
    setattr(t, "_requester_organization_fallback", ben.organization_name)


def _beneficiary_user_ids_map(db: Session, ids: Iterable[str]) -> dict[str, str | None]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = db.execute(select(Beneficiary.id, Beneficiary.user_id).where(Beneficiary.id.in_(ids))).all()
    return {bid: uid for bid, uid in rows}


# ── Multi-assignment hydration ───────────────────────────────────────────────

def _sector_codes_for_ticket(db: Session, ticket_id: str) -> list[str]:
    rows = db.execute(
        select(Sector.code)
        .join(TicketSectorAssignment, TicketSectorAssignment.sector_id == Sector.id)
        .where(TicketSectorAssignment.ticket_id == ticket_id)
        .order_by(TicketSectorAssignment.is_primary.desc(), Sector.code.asc())
    ).all()
    return [code for (code,) in rows]


def _assignees_for_ticket(db: Session, ticket_id: str) -> list[tuple[str, str]]:
    rows = db.execute(
        select(TicketAssignee.user_id, User.username)
        .join(User, User.id == TicketAssignee.user_id)
        .where(TicketAssignee.ticket_id == ticket_id)
        .order_by(TicketAssignee.is_primary.desc(), TicketAssignee.added_at.asc())
    ).all()
    return [(uid, uname or uid) for (uid, uname) in rows]


def _sector_codes_per_ticket(db: Session, ticket_ids: list[str]) -> dict[str, list[str]]:
    if not ticket_ids:
        return {}
    rows = db.execute(
        select(TicketSectorAssignment.ticket_id, Sector.code, TicketSectorAssignment.is_primary)
        .join(Sector, Sector.id == TicketSectorAssignment.sector_id)
        .where(TicketSectorAssignment.ticket_id.in_(ticket_ids))
    ).all()
    out: dict[str, list[tuple[bool, str]]] = {}
    for tid, code, is_primary in rows:
        out.setdefault(tid, []).append((bool(is_primary), code))
    # primary first, then alphabetical
    return {tid: [c for _, c in sorted(items, key=lambda p: (not p[0], p[1]))] for tid, items in out.items()}


def _assignees_per_ticket(db: Session, ticket_ids: list[str]) -> dict[str, list[tuple[str, str]]]:
    if not ticket_ids:
        return {}
    rows = db.execute(
        select(TicketAssignee.ticket_id, TicketAssignee.user_id, User.username, TicketAssignee.is_primary, TicketAssignee.added_at)
        .join(User, User.id == TicketAssignee.user_id)
        .where(TicketAssignee.ticket_id.in_(ticket_ids))
    ).all()
    out: dict[str, list[tuple[bool, str, str, Any]]] = {}
    for tid, uid, uname, is_primary, added_at in rows:
        out.setdefault(tid, []).append((bool(is_primary), uid, uname or uid, added_at))
    return {
        tid: [(uid, uname) for _, uid, uname, _ in sorted(items, key=lambda p: (not p[0], p[3]))]
        for tid, items in out.items()
    }
