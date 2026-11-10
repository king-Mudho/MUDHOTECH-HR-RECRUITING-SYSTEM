"""QuestionResponse.application_id (placeholder UUID since Phase 03) becomes a real FK.

No responses exist before Phase 04, so the column is replaced rather than converted.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
        ("questionnaires", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="questionresponse", name="uniq_response_per_question"),
        migrations.RemoveField(model_name="questionresponse", name="application_id"),
        migrations.AddField(
            model_name="questionresponse",
            name="application",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="responses",
                to="applications.application",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="questionresponse",
            constraint=models.UniqueConstraint(
                fields=("application", "question"), name="uniq_response_per_question"
            ),
        ),
    ]
