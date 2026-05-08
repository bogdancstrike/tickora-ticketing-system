"""Unit tests for src/ticketing/state_machine.py."""
import pytest

from src.ticketing import state_machine as sm


class TestTargetStatus:
    @pytest.mark.parametrize("action,from_status,expected", [
        (sm.ACTION_ASSIGN_SECTOR,   sm.PENDING,            sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_ASSIGN_SECTOR,   sm.ASSIGNED_TO_SECTOR, sm.ASSIGNED_TO_SECTOR),
        (sm.ACTION_ASSIGN_TO_ME,    sm.PENDING,            sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_ME,    sm.ASSIGNED_TO_SECTOR, sm.IN_PROGRESS),
        (sm.ACTION_ASSIGN_TO_ME,    sm.REOPENED,           sm.IN_PROGRESS),
        (sm.ACTION_MARK_DONE,       sm.IN_PROGRESS,        sm.DONE),
        (sm.ACTION_MARK_DONE,       sm.REOPENED,           sm.DONE),
        (sm.ACTION_CLOSE,           sm.DONE,               sm.CLOSED),
        (sm.ACTION_REOPEN,          sm.DONE,               sm.REOPENED),
        (sm.ACTION_REOPEN,          sm.CLOSED,             sm.REOPENED),
        (sm.ACTION_CANCEL,          sm.PENDING,            sm.CANCELLED),
    ])
    def test_valid_transitions(self, action, from_status, expected):
        assert sm.target_status(action, from_status) == expected

    @pytest.mark.parametrize("action,from_status", [
        (sm.ACTION_ASSIGN_TO_ME, sm.CLOSED),
        (sm.ACTION_ASSIGN_TO_ME, sm.DONE),
        (sm.ACTION_MARK_DONE,    sm.PENDING),
        (sm.ACTION_MARK_DONE,    sm.CLOSED),
        (sm.ACTION_CLOSE,        sm.IN_PROGRESS),
        (sm.ACTION_CLOSE,        sm.PENDING),
        (sm.ACTION_REOPEN,       sm.IN_PROGRESS),
        (sm.ACTION_CANCEL,       sm.IN_PROGRESS),
        (sm.ACTION_CANCEL,       sm.DONE),
    ])
    def test_invalid_transitions_return_none(self, action, from_status):
        assert sm.target_status(action, from_status) is None

    def test_unknown_action(self):
        assert sm.target_status("frobnicate", sm.PENDING) is None

    def test_is_valid_matches_target_status(self):
        for action in (sm.ACTION_ASSIGN_TO_ME, sm.ACTION_CLOSE, sm.ACTION_REOPEN):
            for status in sm.ALL_STATUSES:
                expected = sm.target_status(action, status) is not None
                assert sm.is_valid(action, status) is expected
