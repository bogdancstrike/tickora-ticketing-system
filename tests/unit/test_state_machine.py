"""Unit tests for src/ticketing/state_machine.py."""
import pytest

from src.ticketing import state_machine as sm


class TestTargetStatus:
    @pytest.mark.parametrize("action,from_status,expected", [
        (sm.ACTION_ASSIGN_SECTOR,   sm.PENDING,            sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_ASSIGN_SECTOR,   sm.IN_PROGRESS,        sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_ASSIGN_SECTOR,   sm.DONE,               None),
        (sm.ACTION_ASSIGN_TO_ME,    sm.PENDING,            sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_ME,    sm.ASSIGNED_TO_SECTOR, sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_ME,    sm.DONE,               None),
        (sm.ACTION_ASSIGN_TO_USER,  sm.PENDING,            sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_USER,  sm.IN_PROGRESS,        sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_USER,  sm.CANCELLED,          None),
        (sm.ACTION_REASSIGN,        sm.ASSIGNED_TO_SECTOR, sm.IN_PROGRESS),
        (sm.ACTION_REASSIGN,        sm.IN_PROGRESS,        sm.IN_PROGRESS),
        (sm.ACTION_UNASSIGN,        sm.IN_PROGRESS,        sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_UNASSIGN,        sm.PENDING,            None),
        (sm.ACTION_MARK_DONE,       sm.IN_PROGRESS,        sm.DONE),
        (sm.ACTION_MARK_DONE,       sm.ASSIGNED_TO_SECTOR, None),
        (sm.ACTION_CLOSE,           sm.IN_PROGRESS,        sm.DONE),
        (sm.ACTION_CLOSE,           sm.PENDING,            None),
        (sm.ACTION_REOPEN,          sm.DONE,               sm.IN_PROGRESS),
        (sm.ACTION_REOPEN,          sm.CANCELLED,          sm.IN_PROGRESS),
        (sm.ACTION_REOPEN,          sm.PENDING,            None),
        (sm.ACTION_CANCEL,          sm.PENDING,            sm.CANCELLED),
        (sm.ACTION_CANCEL,          sm.IN_PROGRESS,        sm.CANCELLED),
        (sm.ACTION_CANCEL,          sm.DONE,               None),
    ])
    def test_target_status_matrix(self, action, from_status, expected):
        assert sm.target_status(action, from_status) == expected

    def test_unknown_action(self):
        assert sm.target_status("frobnicate", sm.PENDING) is None

    def test_is_valid_matches_target_status(self):
        for action in (sm.ACTION_ASSIGN_TO_ME, sm.ACTION_CLOSE, sm.ACTION_REOPEN, sm.ACTION_CANCEL):
            for status in sm.ALL_STATUSES:
                expected = sm.target_status(action, status) is not None
                assert sm.is_valid(action, status) is expected

    def test_only_five_statuses_exist(self):
        assert sm.ALL_STATUSES == {
            sm.PENDING,
            sm.ASSIGNED_TO_SECTOR,
            sm.IN_PROGRESS,
            sm.DONE,
            sm.CANCELLED,
        }
