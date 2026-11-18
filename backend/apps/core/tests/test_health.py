"""Health checks and pooled connections (ADR-029)."""

from __future__ import annotations

import pytest


@pytest.mark.django_db(transaction=True)
def test_database_check_leaves_no_session_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-029: with pooled connections a session-level statement_timeout would leak into later
    requests (and cancel slow statements, seen as 500s on submit under load)."""
    from django.db import connection

    from apps.core import health

    monkeypatch.setattr(
        connection, "close", lambda: None
    )  # keep the same connection, as a pool would
    health.check_database()
    with connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == "0"
