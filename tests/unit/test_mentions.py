"""Unit tests for `comment_service._extract_mentions`.

The parser is deliberately conservative — username-only, lowercased,
deduped, ignores email addresses. Edge cases here lock the behaviour.
"""
import pytest

from src.ticketing.service.comment_service import _extract_mentions


@pytest.mark.parametrize("body,expected", [
    ("",                                   []),
    (None,                                 []),
    ("plain text",                         []),
    ("hi @alice",                          ["alice"]),
    ("hi @Alice",                          ["alice"]),  # lowercased
    ("hi @alice and @bob",                 ["alice", "bob"]),
    ("hi @alice again @alice",             ["alice"]),  # deduped
    ("foo@bar.com is an email",            []),         # email is not a mention
    ("(@alice) parentheses",               ["alice"]),
    ("[@alice] brackets",                  ["alice"]),
    ("{@alice} braces",                    ["alice"]),
    ("@alice.bobs is one mention",         ["alice.bobs"]),
    ("@alice_001 has digits",              ["alice_001"]),
    ("@alice-name dashed",                 ["alice-name"]),
    ("first line\n@alice on next line",    ["alice"]),
    ("nope email me at me@you.com please", []),
    ("@a longer @b mention @c list",       ["a", "b", "c"]),
])
def test_extract_mentions(body, expected):
    assert _extract_mentions(body) == expected


def test_extract_mentions_caps_username_length():
    """Usernames longer than 32 chars don't match (defends against
    runaway regex captures and aligns with the User model)."""
    too_long = "a" * 50
    assert _extract_mentions(f"@{too_long} ping") == []
