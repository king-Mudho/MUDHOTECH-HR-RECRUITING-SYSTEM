from django.contrib.postgres.operations import CreateExtension, TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """pgvector (embeddings) + pg_trgm (fuzzy search) + unaccent (FTS) - docs/03, ADR-010."""

    dependencies = [("core", "0001_initial")]

    operations = [
        TrigramExtension(),
        CreateExtension("vector"),
        CreateExtension("unaccent"),
    ]
