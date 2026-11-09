from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION mhrs_audit_append_only() RETURNS trigger AS $$
BEGIN
    -- Controlled maintenance (e.g. Phase 09 anonymisation) must opt in explicitly:
    --   SET LOCAL mhrs.audit_maintenance = 'on';
    IF current_setting('mhrs.audit_maintenance', true) = 'on' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;
    RAISE EXCEPTION 'audit tables are append-only (% on %)', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_event_append_only ON audit_auditevent;
CREATE TRIGGER audit_event_append_only BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION mhrs_audit_append_only();

DROP TRIGGER IF EXISTS access_log_append_only ON audit_accesslog;
CREATE TRIGGER access_log_append_only BEFORE UPDATE OR DELETE ON audit_accesslog
    FOR EACH ROW EXECUTE FUNCTION mhrs_audit_append_only();
"""

REVERSE = """
DROP TRIGGER IF EXISTS audit_event_append_only ON audit_auditevent;
DROP TRIGGER IF EXISTS access_log_append_only ON audit_accesslog;
DROP FUNCTION IF EXISTS mhrs_audit_append_only();
"""


class Migration(migrations.Migration):
    """ADR-018: the database itself rejects UPDATE/DELETE on audit rows."""

    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(SQL, REVERSE)]
