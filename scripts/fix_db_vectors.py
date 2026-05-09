import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from src.core.db import get_db
from sqlalchemy import text

def fix():
    print("Connecting to database to purge vector-related objects...")
    with get_db() as db:
        # 1. Find and drop all triggers on the tickets table
        triggers = db.execute(text("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE event_object_table = 'tickets'
        """)).all()
        
        for (tg_name,) in triggers:
            if 'search_vector' in tg_name.lower() or 'tsvector' in tg_name.lower():
                print(f"Dropping trigger: {tg_name}")
                db.execute(text(f"DROP TRIGGER IF EXISTS {tg_name} ON tickets"))

        # 2. Specifically drop the function mentioned in the error
        print("Dropping function: tickets_search_vector_update")
        db.execute(text("DROP FUNCTION IF EXISTS tickets_search_vector_update() CASCADE"))

        # 3. Ensure the column is gone (redundant but safe)
        print("Ensuring search_vector column is dropped...")
        try:
            db.execute(text("ALTER TABLE tickets DROP COLUMN IF EXISTS search_vector CASCADE"))
        except Exception as e:
            print(f"Column drop notice (likely already gone): {e}")

        db.commit()
    print("Purge complete.")

if __name__ == "__main__":
    fix()
