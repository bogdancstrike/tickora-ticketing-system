from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.iam.principal import ROLE_ADMIN, ROLE_EXTERNAL_USER, ROLE_SECTOR_CHIEF, ROLE_INTERNAL_USER, SectorMembership
from src.ticketing.service import dashboard_service
from src.ticketing.models import WidgetDefinition, DashboardWidget, CustomDashboard
from .conftest import create_user, principal_for


def test_sync_widget_catalogue(db_session: Session):
    # Ensure starting clean
    db_session.query(WidgetDefinition).delete()
    db_session.flush()

    dashboard_service.sync_widget_catalogue(db_session)

    count = db_session.query(WidgetDefinition).count()
    # The catalogue grows whenever we ship a new widget type; assert it
    # produced rows and that the well-known seeds exist below.
    assert count >= 15
    
    # Check a few specific ones
    ticket_list = db_session.get(WidgetDefinition, "ticket_list")
    assert ticket_list is not None
    assert ticket_list.display_name == "Ticket List"
    
    welcome = db_session.get(WidgetDefinition, "welcome_banner")
    assert welcome is not None
    assert welcome.is_active is True


def test_auto_configure_admin(db_session: Session):
    admin_user = create_user(db_session, "admin-auto")
    admin_p = principal_for(admin_user, roles={ROLE_ADMIN})
    
    # Create a dashboard
    dash = dashboard_service.create_dashboard(db_session, admin_p, {"title": "Admin Dash"})
    dash_id = dash["id"]
    
    # Auto-configure
    dashboard_service.auto_configure_dashboard(db_session, admin_p, dash_id, mode="replace")
    
    # Verify widgets
    widgets = db_session.query(DashboardWidget).filter_by(dashboard_id=dash_id).all()
    types = {w.type for w in widgets}
    
    # Admin expected: welcome_banner (always), system_health, sla_overview, stale_tickets, bottleneck_analysis, audit_stream
    expected = {"welcome_banner", "system_health", "sla_overview", "stale_tickets", "bottleneck_analysis", "audit_stream"}
    assert expected.issubset(types)
    
    # Verify positions
    welcome = next(w for w in widgets if w.type == "welcome_banner")
    assert welcome.x == 0
    assert welcome.y == 0
    assert welcome.w == 4
    assert welcome.h == 3


def test_auto_configure_beneficiary(db_session: Session):
    user = create_user(db_session, "ben-auto", user_type="external")
    ben_p = principal_for(user, roles={ROLE_EXTERNAL_USER})
    
    # Beneficiaries should now be allowed to have dashboards
    dash = dashboard_service.create_dashboard(db_session, ben_p, {"title": "My Dash"})
    dash_id = dash["id"]
    
    dashboard_service.auto_configure_dashboard(db_session, ben_p, dash_id, mode="replace")
    
    widgets = db_session.query(DashboardWidget).filter_by(dashboard_id=dash_id).all()
    types = {w.type for w in widgets}
    
    # Beneficiary expected: welcome_banner, ticket_list, recent_comments, shortcuts, profile_card
    expected = {"welcome_banner", "ticket_list", "recent_comments", "shortcuts", "profile_card"}
    assert expected.issubset(types)
    
    # Verify config for ticket_list (should be "my requests")
    tl = next(w for w in widgets if w.type == "ticket_list")
    assert tl.config.get("scope") == "my_requests"
