"""RBAC predicates. Single source of truth for "who can do what."

Each predicate is a pure function — no DB or HTTP — so they're trivially testable.
The ticket/comment objects are duck-typed: any object with the named attributes works.
"""
from typing import Protocol

from src.iam.principal import Principal


class _TicketLike(Protocol):
    id: str
    status: str
    beneficiary_type: str
    requester_email: str | None
    current_sector_code: str | None
    assignee_user_id: str | None
    last_active_assignee_user_id: str | None
    created_by_user_id: str | None
    beneficiary_user_id: str | None
    is_deleted: bool


class _CommentLike(Protocol):
    visibility: str  # "public" | "private"
    author_user_id: str | None


# ── Ticket visibility ────────────────────────────────────────────────────────

def can_view_ticket(p: Principal, t: _TicketLike) -> bool:
    """True if `p` may see the existence of ticket `t`."""
    if p.is_admin or p.is_auditor:
        return True
    if _is_requester_by_email(p, t):
        return True
    if t.created_by_user_id and t.created_by_user_id == p.user_id:
        return True
    if t.beneficiary_user_id and t.beneficiary_user_id == p.user_id:
        return True
    if t.current_sector_code and t.current_sector_code in p.all_sectors:
        return True
    if p.is_distributor and t.status in ("pending", "assigned_to_sector"):
        return True
    return False


# ── Ticket mutation ──────────────────────────────────────────────────────────

def can_modify_ticket(p: Principal, t: _TicketLike) -> bool:
    """True if `p` may write fields on `t` (description, priority, resolution, …).

    NOTE: workflow transitions have additional, narrower predicates below.
    """
    if p.is_admin:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    if t.assignee_user_id and t.assignee_user_id == p.user_id:
        return True
    return False


# ── Workflow predicates ──────────────────────────────────────────────────────

def can_assign_sector(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin or p.is_distributor:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    return False


def can_assign_to_me(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin:
        return True
    if t.current_sector_code and t.current_sector_code in p.all_sectors:
        return True
    return False


def can_assign_to_user(p: Principal, t: _TicketLike) -> bool:
    """Manually assign to another user. Distributor, chief of current sector, or admin."""
    if p.is_admin or p.is_distributor:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    return False


def can_reassign(p: Principal, t: _TicketLike) -> bool:
    return can_assign_to_user(p, t)


def can_mark_done(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    if t.assignee_user_id and t.assignee_user_id == p.user_id:
        return True
    return False


def can_close(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin:
        return True
    if _is_requester_by_email(p, t):
        return True
    if t.created_by_user_id and t.created_by_user_id == p.user_id:
        return True
    if t.beneficiary_user_id and t.beneficiary_user_id == p.user_id:
        return True
    return False


def can_reopen(p: Principal, t: _TicketLike) -> bool:
    return can_close(p, t)


def _is_requester_by_email(p: Principal, t: _TicketLike) -> bool:
    return (
        getattr(t, "beneficiary_type", None) == "external"
        and bool(p.email)
        and bool(getattr(t, "requester_email", None))
        and p.email.casefold() == t.requester_email.casefold()
    )


def can_cancel(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin or p.is_distributor:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    return False


def can_change_priority(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin or p.is_distributor:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    return False


# ── Comments ─────────────────────────────────────────────────────────────────

def can_see_private_comments(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin or p.is_auditor or p.is_distributor:
        return True
    if t.current_sector_code and t.current_sector_code in p.all_sectors:
        return True
    return False


def can_post_public_comment(p: Principal, t: _TicketLike) -> bool:
    # Beneficiaries can comment publicly on their own tickets; staff with view rights too.
    if can_view_ticket(p, t):
        return True
    return False


def can_post_private_comment(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin:
        return True
    if t.current_sector_code and t.current_sector_code in p.all_sectors:
        return True
    if p.is_distributor:
        return True
    return False


# ── Attachments ──────────────────────────────────────────────────────────────

def can_upload_attachment(p: Principal, t: _TicketLike) -> bool:
    return can_view_ticket(p, t)


def can_download_attachment(p: Principal, t: _TicketLike, attachment_visibility: str) -> bool:
    if attachment_visibility == "public":
        return can_view_ticket(p, t)
    return can_see_private_comments(p, t)


# ── Admin / audit ────────────────────────────────────────────────────────────

def can_administer(p: Principal) -> bool:
    return p.is_admin


def can_view_global_audit(p: Principal) -> bool:
    return p.is_admin or p.is_auditor


def can_view_sector_audit(p: Principal, sector_code: str) -> bool:
    return p.is_admin or p.is_auditor or p.is_chief_of(sector_code)


def can_view_global_dashboard(p: Principal) -> bool:
    return p.is_admin or p.is_auditor


def can_view_sector_dashboard(p: Principal, sector_code: str) -> bool:
    return p.is_admin or p.is_auditor or p.is_chief_of(sector_code) or p.is_member_of(sector_code)
