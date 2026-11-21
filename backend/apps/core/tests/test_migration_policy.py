"""EC-OPS-05: migrations on live tables are expand/contract, and new indexes are built concurrently.

Deploys run migrations while the previous release is still serving (docs/10 section 4), so a
migration must never break the code that is running:

- **expand only** in a release: no RemoveField / DeleteModel / RenameField / RenameModel /
  AlterUniqueTogether removals; the matching "contract" step ships in a later release, listed in
  CONTRACT_ALLOWED with the release that stopped using the column;
- **no table locks** for indexes: AddIndex on an existing table locks writes for the whole build,
  so new migrations use ``AddIndexConcurrently`` (with ``atomic = False``).

Migrations that existed at v1.2.0 are the baseline (``migration_baseline.txt``); the rules apply to
everything added after it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations
from django.db.migrations.loader import MigrationLoader

BASELINE = {
    line.strip()
    for line in (Path(__file__).with_name("migration_baseline.txt")).read_text().splitlines()
    if line.strip() and not line.startswith("#")
}
DESTRUCTIVE = (
    migrations.RemoveField,
    migrations.DeleteModel,
    migrations.RenameField,
    migrations.RenameModel,
)
# "app.migration": "reason / release that stopped using it" - contract steps reviewed by a person
CONTRACT_ALLOWED: dict[str, str] = {}


def _new_migrations() -> list[tuple[str, migrations.Migration]]:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return [
        (f"{app}.{name}", migration)
        for (app, name), migration in sorted(loader.disk_migrations.items())
        if migration.__module__.startswith("apps.") and f"{app}.{name}" not in BASELINE
    ]


def _created_models(migration: migrations.Migration) -> set[str]:
    return {
        op.name.lower() for op in migration.operations if isinstance(op, migrations.CreateModel)
    }


def test_baseline_lists_real_migrations() -> None:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    on_disk = {f"{a}.{n}" for (a, n) in loader.disk_migrations}
    assert len(BASELINE) >= 70
    missing = sorted(BASELINE - on_disk)
    assert not missing, f"baseline names missing on disk: {missing[:5]}"


@pytest.mark.parametrize("label,migration", _new_migrations() or [("none", None)])
def test_new_migrations_are_expand_only(label: str, migration: migrations.Migration | None) -> None:
    if migration is None:
        return
    destructive = [type(op).__name__ for op in migration.operations if isinstance(op, DESTRUCTIVE)]
    assert not destructive or label in CONTRACT_ALLOWED, (
        f"{label} contains {destructive}: ship the contract step in a later release and list it in "
        "CONTRACT_ALLOWED with the reason (EC-OPS-05)"
    )


@pytest.mark.parametrize("label,migration", _new_migrations() or [("none", None)])
def test_new_indexes_on_existing_tables_are_concurrent(
    label: str, migration: migrations.Migration | None
) -> None:
    if migration is None:
        return
    new_tables = _created_models(migration)
    locking = [
        op.model_name
        for op in migration.operations
        if isinstance(op, migrations.AddIndex)
        and not isinstance(op, AddIndexConcurrently)
        and op.model_name.lower() not in new_tables  # indexing a table created here is fine
    ]
    assert not locking, (
        f"{label} adds indexes to existing tables {locking} with AddIndex, which locks writes: use "
        "AddIndexConcurrently and set atomic = False (EC-OPS-05)"
    )
    if any(isinstance(op, AddIndexConcurrently) for op in migration.operations):
        assert migration.atomic is False, f"{label}: AddIndexConcurrently needs atomic = False"
