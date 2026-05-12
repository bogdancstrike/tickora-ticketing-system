"""Ticket workflow state machine.

A pure data structure: actions × source-statuses → target-status. Service
code consults this table before issuing the SQL transition. The atomic UPDATE
is the runtime enforcement; this table is the design enforcement.
"""
from dataclasses import dataclass

# Statuses (BRD §11.2 — trimmed set)
PENDING             = "pending"
ASSIGNED_TO_SECTOR  = "assigned_to_sector"
IN_PROGRESS         = "in_progress"
DONE                = "done"
CANCELLED           = "cancelled"

ALL_STATUSES = frozenset({
    PENDING, ASSIGNED_TO_SECTOR, IN_PROGRESS,
    DONE, CANCELLED,
})

ACTIVE_STATUSES = (PENDING, ASSIGNED_TO_SECTOR, IN_PROGRESS)
DONE_STATUSES = (DONE,)

# Actions
ACTION_ASSIGN_SECTOR    = "assign_sector"
ACTION_ASSIGN_TO_ME     = "assign_to_me"
ACTION_ASSIGN_TO_USER   = "assign_to_user"
ACTION_REASSIGN         = "reassign"
ACTION_UNASSIGN         = "unassign"
ACTION_MARK_DONE        = "mark_done"
ACTION_CLOSE            = "close"
ACTION_REOPEN           = "reopen"
ACTION_CANCEL           = "cancel"
ACTION_CHANGE_STATUS    = "change_status"


@dataclass(frozen=True)
class Transition:
    action: str
    from_statuses: frozenset[str]
    to_status: str


# from_status × action → to_status
ASSIGNABLE_STATUSES = frozenset({PENDING, ASSIGNED_TO_SECTOR})
WORKABLE_STATUSES = frozenset({PENDING, ASSIGNED_TO_SECTOR, IN_PROGRESS})
IN_PROGRESS_ONLY = frozenset({IN_PROGRESS})
FINISHED_STATUSES = frozenset({DONE, CANCELLED})


TRANSITIONS: list[Transition] = [
    Transition(ACTION_ASSIGN_SECTOR,   WORKABLE_STATUSES, ASSIGNED_TO_SECTOR),
    Transition(ACTION_ASSIGN_TO_ME,    ASSIGNABLE_STATUSES, IN_PROGRESS),
    Transition(ACTION_ASSIGN_TO_USER,  WORKABLE_STATUSES, IN_PROGRESS),
    Transition(ACTION_REASSIGN,        WORKABLE_STATUSES, IN_PROGRESS),
    Transition(ACTION_UNASSIGN,        IN_PROGRESS_ONLY, ASSIGNED_TO_SECTOR),
    Transition(ACTION_MARK_DONE,       IN_PROGRESS_ONLY, DONE),
    Transition(ACTION_CLOSE,           IN_PROGRESS_ONLY, DONE),
    Transition(ACTION_REOPEN,          FINISHED_STATUSES, IN_PROGRESS),
    Transition(ACTION_CANCEL,          WORKABLE_STATUSES, CANCELLED),
]

_BY_ACTION: dict[str, Transition] = {t.action: t for t in TRANSITIONS}


def target_status(action: str, current_status: str) -> str | None:
    """Return the target status if `action` is valid from `current_status`, else None."""
    t = _BY_ACTION.get(action)
    if t is None:
        return None
    if current_status not in t.from_statuses:
        return None
    return t.to_status


def is_valid(action: str, current_status: str) -> bool:
    return target_status(action, current_status) is not None
