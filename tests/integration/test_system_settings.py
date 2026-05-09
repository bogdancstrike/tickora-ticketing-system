import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from src.ticketing.models import SystemSetting

def test_system_setting_model(db_session: Session):
    # Create a setting
    setting = SystemSetting(
        key="test_key",
        value={"foo": "bar"},
        description="Test Description"
    )
    db_session.add(setting)
    db_session.commit()

    # Query it back
    retrieved = db_session.get(SystemSetting, "test_key")
    assert retrieved is not None
    assert retrieved.value == {"foo": "bar"}
    assert retrieved.description == "Test Description"
    assert isinstance(retrieved.updated_at, datetime)

def test_system_setting_update(db_session: Session):
    setting = SystemSetting(
        key="autopilot_max_widgets",
        value={"limit": 20}
    )
    db_session.add(setting)
    db_session.commit()

    # Update
    setting.value = {"limit": 30}
    db_session.commit()

    retrieved = db_session.get(SystemSetting, "autopilot_max_widgets")
    assert retrieved.value == {"limit": 30}
