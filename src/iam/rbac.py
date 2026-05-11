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
    assignee_user_ids: list[str]
    last_active_assignee_user_id: str | None
    created_by_user_id: str | None
    beneficiary_user_id: str | None
    sector_codes: list[str]
    is_deleted: bool


class _CommentLike(Protocol):
    visibility: str  # "public" | "private"
    author_user_id: str | None


def _sector_codes(t: _TicketLike) -> set[str]:
    codes = set(getattr(t, "sector_codes", []) or [])
    if t.current_sector_code:
        codes.add(t.current_sector_code)
    return codes


def _assignee_user_ids(t: _TicketLike) -> set[str]:
    user_ids = set(getattr(t, "assignee_user_ids", []) or [])
    if t.assignee_user_id:
        user_ids.add(t.assignee_user_id)
    return user_ids


def _is_assigned_to(p: Principal, t: _TicketLike) -> bool:
    return bool(p.user_id and p.user_id in _assignee_user_ids(t))


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
    if _sector_codes(t).intersection(p.all_sectors):
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
    if _is_assigned_to(p, t):
        return True
    return False


# ── Workflow predicates ──────────────────────────────────────────────────────

def can_assign_sector(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin or p.is_distributor:
        return True
    if t.current_sector_code and p.is_chief_of(t.current_sector_code):
        return True
    return False


def can_remove_sector(p: Principal, t: _TicketLike, sector_code: str) -> bool:
    """Detach a sector. Restricted to admins, distributors, or the chief of that sector."""
    if p.is_admin or p.is_distributor:
        return True
    if p.is_chief_of(sector_code):
        return True
    return False


def can_assign_to_me(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin:
        return True
    if _sector_codes(t).intersection(p.all_sectors):
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
    """Operator-side "done" transition.

    Policy: only the user(s) who pulled the ticket onto themselves (self-
    assignment) can mark it done. Admins retain an override so support can
    unstick an abandoned ticket. Chiefs deliberately do **not** get this
    capability — if a chief wants to act on a ticket they must self-assign
    first, which keeps the audit trail honest about who actually did the
    work.
    """
    if p.is_admin:
        return True
    if _is_assigned_to(p, t):
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


def can_drive_status(p: Principal, t: _TicketLike) -> bool:
    """True if `p` may push the ticket through operator-side transitions
    (in_progress, mark_done, etc.).

    Policy: only the active assignee can drive status. Self-assignment
    (`can_assign_to_me` -> `assign_to_me`) is the gateway for sector members,
    so a member who wants to work a ticket pulls it first. Admins retain an
    override; distributors keep their narrow triage lane via `can_cancel`
    and `can_assign_sector`.
    """
    if p.is_admin:
        return True
    if _is_assigned_to(p, t):
        return True
    return False


# ── Comments ─────────────────────────────────────────────────────────────────

def can_see_private_comments(p: Principal, t: _TicketLike) -> bool:
    if p.is_admin or p.is_auditor or p.is_distributor:
        return True
    if _sector_codes(t).intersection(p.all_sectors):
        return True
    return False


def can_post_public_comment(p: Principal, t: _TicketLike) -> bool:
    """Public comments are limited to people actually working or affected by
    the ticket:

      * the active assignee (self-assigned), and
      * the beneficiary side — creator, internal beneficiary, or external
        requester-by-email.

    Admins keep an override for support cases. Distributors and sector
    chiefs/members who haven't self-assigned can still read but can't post —
    if they want to participate they self-assign first, which keeps the
    discussion attributable to the operator on the hook.
    """
    if p.is_admin:
        return True
    if _is_assigned_to(p, t):
        return True
    if t.created_by_user_id and t.created_by_user_id == p.user_id:
        return True
    if t.beneficiary_user_id and t.beneficiary_user_id == p.user_id:
        return True
    if _is_requester_by_email(p, t):
        return True
    return False


def can_post_private_comment(p: Principal, t: _TicketLike) -> bool:
    """Private (staff-only) comments are restricted to:

      * admins,
      * distributors during triage (they need a place to leave routing notes
        before any sector member touches the ticket),
      * the active assignee — sector members who self-assigned the ticket.

    Sector members who haven't self-assigned no longer qualify. This stops a
    bystander from leaving private notes on tickets they aren't actively
    working.
    """
    if p.is_admin:
        return True
    if p.is_distributor:
        return True
    if _is_assigned_to(p, t):
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


def can_delete_ticket(p: Principal, t: _TicketLike) -> bool:
    """Only super-admins can soft-delete tickets."""
    return is_super_admin(p)


def can_update_ticket(p: Principal, t: _TicketLike) -> bool:
    """Admins or anyone with update permission (e.g. distributor during triage)."""
    return p.is_admin or p.is_distributor or (t.current_sector_code and p.is_chief_of(t.current_sector_code))


def can_view_audit_tab(p: Principal, t: _TicketLike) -> bool:
    """Only staff working on the ticket (and admins/auditors) see the audit tab."""
    if p.is_admin or p.is_auditor:
        return True
    if _sector_codes(t).intersection(p.all_sectors):
        return True
    if p.is_distributor:
        return True
    return False


# ── Endorsements (avizare suplimentară) ─────────────────────────────────────

def can_request_endorsement(p: Principal, t: _TicketLike) -> bool:
    """Only the active assignee (or admin) can ask for a supplementary
    endorsement. Bystander chiefs/members must self-assign first — same
    policy as comment writes and operator-side status transitions."""
    if p.is_admin:
        return True
    if _is_assigned_to(p, t):
        return True
    return False


class _EndorsementLike(Protocol):
    assigned_to_user_id: str | None
    status: str


def can_decide_endorsement(p: Principal, e: _EndorsementLike) -> bool:
    """Admin override, plus any avizator on a pool request, plus the
    specific avizator a direct request targets."""
    if p.is_admin:
        return True
    if not p.is_avizator:
        return False
    if e.assigned_to_user_id is None:           # pool request
        return True
    return e.assigned_to_user_id == p.user_id


def is_super_admin(p: Principal) -> bool:
    """Super-admin gate for sensitive operations (e.g. permanent deletion).

    The list of allowed subjects is configured via ``Config.SUPER_ADMIN_SUBJECTS``
    (env var ``SUPER_ADMIN_SUBJECTS``, comma-separated). Importing the config
    lazily avoids a circular import at module load.
    """
    from src.config import Config  # local import to dodge circulars
    return p.is_admin and p.keycloak_subject in Config.SUPER_ADMIN_SUBJECTS
