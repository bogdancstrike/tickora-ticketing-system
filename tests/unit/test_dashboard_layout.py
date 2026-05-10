"""Unit tests for the dashboard auto-layout packer + recipe selection."""
from __future__ import annotations

import pytest

from src.iam.principal import (
    Principal,
    SectorMembership,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_DISTRIBUTOR,
    ROLE_EXTERNAL_USER,
    ROLE_INTERNAL_USER,
)
from src.ticketing.service.dashboard_service import (
    _GRID_WIDTH,
    _SIZES,
    _pack,
    _pick_recipe,
)


def _principal(*, roles: tuple[str, ...] = (), sectors: tuple[SectorMembership, ...] = (), user_type: str = "internal") -> Principal:
    return Principal(
        user_id="u-self",
        keycloak_subject="kc-self",
        username="self",
        email="self@x",
        user_type=user_type,
        global_roles=frozenset(roles),
        sector_memberships=sectors,
    )


# ── Packer ──────────────────────────────────────────────────────────────────

class TestPack:
    def test_empty_input_returns_empty(self):
        assert _pack([]) == []

    def test_default_size_is_md(self):
        out = _pack([{"type": "x"}])
        assert (out[0]["w"], out[0]["h"]) == _SIZES["md"]

    def test_unknown_size_falls_back_to_md(self):
        out = _pack([{"type": "x", "size": "unknown"}])
        assert (out[0]["w"], out[0]["h"]) == _SIZES["md"]

    def test_full_row_packs_in_order(self):
        out = _pack([
            {"type": "a", "size": "sm"},  # 4x3
            {"type": "b", "size": "sm"},  # 4x3
            {"type": "c", "size": "sm"},  # 4x3 — 12 wide together
        ])
        assert [(w["x"], w["y"]) for w in out] == [(0, 0), (4, 0), (8, 0)]

    def test_wraps_when_row_full(self):
        out = _pack([
            {"type": "a", "size": "lg"},  # 8x4
            {"type": "b", "size": "md"},  # 6x4 — doesn't fit, wraps
        ])
        assert (out[0]["x"], out[0]["y"]) == (0, 0)
        assert (out[1]["x"], out[1]["y"]) == (0, 4)

    def test_row_height_is_max_of_row(self):
        out = _pack([
            {"type": "a", "size": "sm"},  # 4x3
            {"type": "b", "size": "lg"},  # 8x4 — fills row, h=4
            {"type": "c", "size": "md"},  # 6x4 — wraps
        ])
        # First two share a row of height 4; the wrap lands on y=4.
        assert out[0]["y"] == 0
        assert out[1]["y"] == 0
        assert out[2]["y"] == 4

    def test_xl_consumes_full_row(self):
        out = _pack([
            {"type": "a", "size": "xl"},  # 12x4
            {"type": "b", "size": "sm"},
        ])
        assert (out[0]["x"], out[0]["y"], out[0]["w"]) == (0, 0, _GRID_WIDTH)
        assert (out[1]["x"], out[1]["y"]) == (0, 4)

    def test_pre_positioned_widget_skips_packer(self):
        out = _pack([
            {"type": "a", "x": 7, "y": 9, "w": 5, "h": 2, "size": "md"},
        ])
        assert (out[0]["x"], out[0]["y"], out[0]["w"], out[0]["h"]) == (7, 9, 5, 2)

    def test_no_widget_overflows_grid(self):
        out = _pack([{"type": f"w{i}", "size": "md"} for i in range(20)])
        for w in out:
            assert w["x"] + w["w"] <= _GRID_WIDTH
            assert w["x"] >= 0
            assert w["y"] >= 0


# ── Recipe selection ────────────────────────────────────────────────────────

class TestPickRecipe:
    def test_admin_wins_over_everything(self):
        p = _principal(
            roles=(ROLE_ADMIN, ROLE_AUDITOR, ROLE_DISTRIBUTOR),
            sectors=(SectorMembership("s10", "chief"),),
        )
        recipe = _pick_recipe(p, None)
        assert any(w["type"] == "active_sessions" for w in recipe), \
            "admin recipe must include the active-sessions widget"

    def test_auditor_when_no_admin(self):
        p = _principal(roles=(ROLE_AUDITOR,))
        recipe = _pick_recipe(p, None)
        types = {w["type"] for w in recipe}
        assert "audit_stream" in types
        assert "active_sessions" not in types  # auditors get a smaller set

    def test_distributor_recipe(self):
        p = _principal(roles=(ROLE_DISTRIBUTOR, ROLE_INTERNAL_USER))
        recipe = _pick_recipe(p, None)
        types = [w["type"] for w in recipe]
        assert "not_reviewed" in types
        assert "reviewed_today" in types

    def test_chief_picks_primary_sector(self):
        p = _principal(
            roles=(ROLE_INTERNAL_USER,),
            sectors=(SectorMembership("s10", "chief"), SectorMembership("s2", "chief")),
        )
        recipe = _pick_recipe(p, "s10")
        # The first widget references the chosen sector.
        sector_widgets = [w for w in recipe if (w.get("config") or {}).get("sector_code")]
        assert sector_widgets
        for w in sector_widgets:
            assert w["config"]["sector_code"] == "s10"

    def test_chief_defaults_to_alphabetic_sector(self):
        p = _principal(
            roles=(ROLE_INTERNAL_USER,),
            sectors=(SectorMembership("s9", "chief"), SectorMembership("s2", "chief")),
        )
        recipe = _pick_recipe(p, None)  # no primary_sector hint
        sector_widgets = [w for w in recipe if (w.get("config") or {}).get("sector_code")]
        # `sorted(p.chief_sectors)[0]` → "s2"
        for w in sector_widgets:
            assert w["config"]["sector_code"] == "s2"

    def test_member_recipe_has_personal_widgets(self):
        p = _principal(
            roles=(ROLE_INTERNAL_USER,),
            sectors=(SectorMembership("s10", "member"),),
        )
        recipe = _pick_recipe(p, None)
        types = {w["type"] for w in recipe}
        assert {"my_assigned", "my_watchlist", "my_mentions"} <= types

    def test_external_beneficiary_gets_beneficiary_recipe(self):
        p = _principal(roles=(ROLE_EXTERNAL_USER,), user_type="external")
        recipe = _pick_recipe(p, None)
        types = {w["type"] for w in recipe}
        assert "my_requests" in types
        # No staff widgets.
        assert "audit_stream" not in types
        assert "task_health" not in types
