"""PostgreSQL row-level security as a second line of tenant defence (P09-T07, ADR-012).

Each major tenant table gets a policy that, *when the request has set* ``app.current_org``, only
lets rows of that organisation be read or written. Without the setting (system tasks, candidate
endpoints, platform tools, migrations) the policy allows everything, so application-level scoping
(``for_org``) stays the primary control and RLS catches a forgotten filter in staff APIs.
``FORCE`` applies the policy to the table owner too (the app connects as the owner).
"""

from django.db import migrations

TABLES = (
    "applications_application",
    "applications_applicationdocument",
    "applications_applicationnote",
    "applications_applicationstatusevent",
    "messaging_clarificationrequest",
    "messaging_message",
    "messaging_messagethread",
    "questionnaires_questionresponse",
    "resumes_claimcorrection",
    "resumes_documenttext",
    "resumes_extractedclaim",
    "resumes_extractionrun",
    "screening_criterionresult",
    "screening_evaluation",
    "screening_evaluationevidence",
    "screening_humanverification",
    "screening_screeningrun",
    "shortlisting_shortlist",
    "shortlisting_shortlistentry",
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
        ("core", "0002_postgres_extensions"),
        ("applications", "0010_conflicts_full_pool"),
        ("messaging", "0001_initial"),
        ("questionnaires", "0002_questionresponse_application_fk"),
        ("resumes", "0002_resume_parse"),
        ("screening", "0002_model_registry_quality"),
        ("shortlisting", "0001_initial"),
    ]

    operations = [migrations.RunSQL(forwards_sql(), backwards_sql())]
