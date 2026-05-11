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
from src.ticketing.models import Category, MetadataKeyDefinition, Sector, Subcategory, SystemSetting
from src.ticketing.service import dashboard_service

def seed_sectors(db) -> None:
    sectors = [
        ("s1",  "Service Desk"),
        ("s2",  "Network Operations"),
        ("s3",  "Infrastructure"),
        ("s4",  "Applications"),
        ("s5",  "Security"),
        ("s6",  "Database Administration"),
        ("s7",  "Cloud Services"),
        ("s8",  "DevOps & CI/CD"),
        ("s9",  "Quality Assurance"),
        ("s10", "Field Operations"),
    ]
    for code, name in sectors:
        s = db.scalar(select(Sector).where(Sector.code == code))
        if not s:
            db.add(Sector(code=code, name=name, description=f"Production {name}"))
    db.flush()
    print("[prod:sectors] default sectors seeded")

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

def seed_categories(db) -> None:
    categories = [
        {
            "code": "infra",
            "name": "Infrastructure",
            "subcategories": [
                {"code": "network", "name": "Network Connectivity"},
                {"code": "hardware", "name": "Hardware Failure"},
                {"code": "datacenter", "name": "Datacenter Access"},
            ]
        },
        {
            "code": "apps",
            "name": "Applications",
            "subcategories": [
                {"code": "bug", "name": "Software Bug"},
                {"code": "access", "name": "Access Request"},
                {"code": "feature", "name": "Feature Request"},
            ]
        },
        {
            "code": "security",
            "name": "Security",
            "subcategories": [
                {"code": "incident", "name": "Security Incident"},
                {"code": "audit", "name": "Audit Request"},
            ]
        }
    ]
    for c_spec in categories:
        c = db.scalar(select(Category).where(Category.code == c_spec["code"]))
        if not c:
            c = Category(code=c_spec["code"], name=c_spec["name"])
            db.add(c)
            db.flush()

        for s_spec in c_spec["subcategories"]:
            s = db.scalar(select(Subcategory).where(Subcategory.category_id == c.id, Subcategory.code == s_spec["code"]))
            if not s:
                db.add(Subcategory(category_id=c.id, code=s_spec["code"], name=s_spec["name"]))
    db.flush()
    print("[prod:categories] default categories and subcategories seeded")

def main() -> int:
    with get_db() as db:
        # 1. Sync Widget Catalogue
        dashboard_service.sync_widget_catalogue(db)
        print("[prod:widgets] widget catalogue synchronized")

        # 2. Seed System Settings
        seed_system_settings(db)

        # 3. Seed Metadata Keys
        seed_metadata_keys(db)

        # 4. Seed Categories
        seed_categories(db)

        # 5. Seed Sectors
        seed_sectors(db)

        db.commit()
    print("production seeding complete.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
