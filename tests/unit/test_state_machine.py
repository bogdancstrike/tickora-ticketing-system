"""Unit tests for src/ticketing/state_machine.py."""
import pytest

from src.ticketing import state_machine as sm


class TestTargetStatus:
    @pytest.mark.parametrize("action,expected", [
        (sm.ACTION_ASSIGN_SECTOR,   sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_ASSIGN_TO_ME,    sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_USER,  sm.IN_PROGRESS),
        (sm.ACTION_REASSIGN,        sm.IN_PROGRESS),
        (sm.ACTION_UNASSIGN,        sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_MARK_DONE,       sm.DONE),
        (sm.ACTION_CLOSE,           sm.DONE),
        (sm.ACTION_REOPEN,          sm.IN_PROGRESS),
        (sm.ACTION_CANCEL,          sm.CANCELLED),
    ])
    def test_actions_are_valid_from_every_status(self, action, expected):
        for from_status in sm.ALL_STATUSES:
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
