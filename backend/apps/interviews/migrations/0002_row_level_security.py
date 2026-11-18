"""Row-level security on the interview tables (ADR-012), same policy as core.0003."""

from django.db import migrations

TABLES = (
    "interviews_scorecardtemplate",
    "interviews_interview",
    "interviews_interviewslot",
    "interviews_interviewpanelist",
    "interviews_scorecard",
)
CONDITION = (
    "coalesce(current_setting('app.current_org', true), '') = '' "
    "OR organisation_id::text = current_setting('app.current_org', true)"
)


def forwards_sql() -> list[str]:
    sql = []
    for table in TABLES:
        sql += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
            f"CREATE POLICY tenant_isolation ON {table} USING ({CONDITION}) WITH CHECK ({CONDITION})",
        ]
    return sql


def backwards_sql() -> list[str]:
    sql = []
    for table in TABLES:
        sql += [
            f"DROP POLICY IF EXISTS tenant_isolation ON {table}",
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        ]
    return sql


class Migration(migrations.Migration):
    dependencies = [
        ("interviews", "0001_initial"),
        ("core", "0003_row_level_security"),
    ]

    operations = [migrations.RunSQL(forwards_sql(), backwards_sql())]
