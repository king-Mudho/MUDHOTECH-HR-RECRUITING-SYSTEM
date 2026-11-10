"""Application status events are append-only at the database level (reuses the audit trigger)."""

from django.db import migrations

SQL = """
CREATE TRIGGER application_status_event_append_only
BEFORE UPDATE OR DELETE ON applications_applicationstatusevent
FOR EACH ROW EXECUTE FUNCTION mhrs_audit_append_only();
"""
REVERSE = "DROP TRIGGER IF EXISTS application_status_event_append_only ON applications_applicationstatusevent;"


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
        ("audit", "0002_append_only_triggers"),
    ]

    operations = [migrations.RunSQL(SQL, REVERSE)]
