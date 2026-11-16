"""Backfill the essentials counts of already-evaluated applications (P08-T05). Idempotent."""

from typing import Any

from django.db import migrations


def backfill(apps: Any, schema_editor: Any) -> None:
    Application = apps.get_model("applications", "Application")
    Evaluation = apps.get_model("screening", "Evaluation")
    rows = Application.objects.filter(current_evaluation_id__isnull=False).exclude(
        ai_band="manual_review_requested"
    )
    for app in rows.iterator():
        evaluation = Evaluation.objects.filter(pk=app.current_evaluation_id).first()
        if evaluation is None:
            continue
        ess = evaluation.essentials or {}
        Application.objects.filter(pk=app.pk).update(
            essentials_met=len(ess.get("met", [])) + len(ess.get("partial", [])),
            essentials_unknown=len(ess.get("unknown", [])),
            essentials_not_evidenced=len(ess.get("not_evidenced", [])),
        )
    Application.objects.filter(ai_band="manual_review_requested").update(
        score=None, coverage=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0008_applicants_table"),
        ("screening", "0002_model_registry_quality"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
