#!/usr/bin/env python3
"""Seed production configuration data in Postgres.

This script only seeds data required for the system to function correctly
(metadata definitions, widget catalogue, system settings). No mock tickets or users.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select, text
from src.core.db import get_db
from src.ticketing.models import MetadataKeyDefinition, SystemSetting
from src.ticketing.service import dashboard_service

def seed_system_settings(db) -> None:
    settings = [
        ("autopilot_max_widgets", 20, "Maximum number of widgets allowed per dashboard during auto-configuration."),
        ("autopilot_max_ticket_watchers", 5, "Maximum number of specific ticket comment watchers to add during auto-configuration."),
    ]
    for key, value, desc in settings:
        s = db.get(SystemSetting, key)
        if not s:
            db.add(SystemSetting(key=key, value=value, description=desc))
        else:
            s.description = desc
    db.flush()
    print("[prod:settings] system settings seeded")

def seed_metadata_keys(db) -> None:
    keys = [
        ("importance", "Importance Level", "string", ["low", "standard", "vip"], "Business priority label"),
        ("platform", "Platform", "string", ["web", "mobile", "desktop", "api"], "Source platform of the request"),
        ("environment", "Environment", "string", ["prod", "stage", "dev"], "Target environment for the issue"),
    ]
    for key, label, vtype, options, desc in keys:
        k = db.get(MetadataKeyDefinition, key)
        if not k:
            db.add(MetadataKeyDefinition(key=key, label=label, value_type=vtype, options=options, description=desc))
    db.flush()
    print("[prod:metadata] default metadata keys seeded")

def main() -> int:
    with get_db() as db:
        # 1. Sync Widget Catalogue
        dashboard_service.sync_widget_catalogue(db)
        print("[prod:widgets] widget catalogue synchronized")
        
        # 2. Seed System Settings
        seed_system_settings(db)
        
        # 3. Seed Metadata Keys
        seed_metadata_keys(db)
        
        db.commit()
    print("production seeding complete.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
