from src.core.db import get_db
from sqlalchemy import text

def cleanup():
    with get_db() as db:
        tables = [
            'custom_dashboards', 'dashboard_widgets', 'dashboard_shares', 'user_dashboard_settings',
            'widget_definitions', 'system_settings', 'metadata_key_definitions', 'ticket_metadatas',
            'ticket_comments', 'ticket_attachments', 'ticket_status_history', 'ticket_sector_history',
            'ticket_assignment_history', 'ticket_links', 'ticket_sectors', 'ticket_assignees',
            'audit_events', 'notifications', 'tickets', 'beneficiaries',
            'sector_memberships', 'sectors', 'users'
        ]
        print("Truncating tables...")
        db.execute(text(f'TRUNCATE {", ".join(tables)} CASCADE'))
        db.commit()
    print("Database cleared successfully.")

if __name__ == "__main__":
    cleanup()
