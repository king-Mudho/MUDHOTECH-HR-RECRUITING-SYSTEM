"""Health checks, feature flags, base task / dead letters, management commands."""

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest import mock

import pytest
from celery import shared_task
from django.core import mail
from django.core.management import call_command

from apps.core import flags, health
from apps.core.models import DeadLetter
from apps.core.tasks import BaseTask, ping

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------- health
def test_healthz(client: Any) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


def test_readyz_ok_when_all_checks_pass(client: Any) -> None:
    with mock.patch.dict(
        health.CHECKS, {"database": lambda: None, "redis": lambda: None, "storage": lambda: None}
    ):
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert set(resp.json()["checks"]) == {"database", "redis", "storage"}


def test_readyz_503_when_dependency_down(client: Any) -> None:
    def down() -> None:
        raise ConnectionError("refused")

    with mock.patch.dict(
        health.CHECKS, {"database": lambda: None, "redis": down, "storage": lambda: None}
    ):
        resp = client.get("/readyz")
    body = resp.json()
    assert resp.status_code == 503
    assert body["status"] == "unavailable"
    assert body["checks"]["redis"] == {
        "status": "error",
        "error": "ConnectionError",
        "latency_ms": mock.ANY,
    }


def test_readyz_check_timeout(settings: Any) -> None:
    import time as _t

    settings.HEALTHCHECK_TIMEOUT_SECONDS = 0.05
    results = health.run_checks({"slow": lambda: _t.sleep(0.3)})
    assert results["slow"]["error"] == "timeout"


@pytest.mark.django_db(transaction=True)
def test_database_check_real() -> None:
    health.check_database()


def test_redis_check_uses_timeouts(settings: Any) -> None:
    settings.CELERY_BROKER_URL = "redis://127.0.0.1:1/0"
    settings.HEALTHCHECK_TIMEOUT_SECONDS = 0.2
    with pytest.raises(Exception):  # noqa: B017
        health.check_redis()


def test_storage_check_delegates() -> None:
    with mock.patch("apps.core.storage.check_bucket") as cb:
        health.check_storage()
    cb.assert_called_once_with("documents")


# ---------------------------------------------------------------- feature flags
def test_flags_default_global_and_org_override(org: Any, other_org: Any) -> None:
    assert flags.is_enabled("ai.llm") is False
    assert flags.is_enabled("ai.llm", default=True) is True
    flags.set_flag("ai.llm", True)
    assert flags.is_enabled("ai.llm") is True
    flags.set_flag("ai.llm", False, org=org)
    assert flags.is_enabled("ai.llm", org=org) is False
    assert flags.is_enabled("ai.llm", org=other_org) is True
    assert flags.is_enabled("ai.llm", org=other_org.pk) is True


def test_flags_are_cached_and_invalidated_on_save() -> None:
    flags.set_flag("x.cached", True)
    assert flags.is_enabled("x.cached")
    with mock.patch("apps.core.flags.FeatureFlag.objects.filter") as q:
        assert flags.is_enabled("x.cached")  # served from cache
        q.assert_not_called()
    flags.set_flag("x.cached", False)  # post_save invalidates
    assert flags.is_enabled("x.cached") is False


# ---------------------------------------------------------------- base task / dead letters
@shared_task(name="tests.always_fails", base=BaseTask, max_retries=0)
def always_fails(x: int, organisation_id: str | None = None) -> None:
    raise ValueError(f"bad {x}")


def test_base_task_options() -> None:
    assert BaseTask.acks_late is True
    assert BaseTask.reject_on_worker_lost is True
    assert BaseTask.max_retries == 3
    assert BaseTask.retry_backoff == 30


def test_final_failure_writes_dead_letter(settings: Any, org: Any) -> None:
    settings.CELERY_TASK_EAGER_PROPAGATES = False
    result = always_fails.apply(args=[7], kwargs={"organisation_id": str(org.pk)})
    assert result.failed()
    dl = DeadLetter.objects.get(task_name="tests.always_fails")
    assert dl.args == [7]
    assert "ValueError: bad 7" in dl.error
    assert dl.organisation_id == org.pk
    assert "Traceback" in dl.traceback


def test_ping_task() -> None:
    assert ping.apply().get() == "pong"


def test_task_context_signals_set_and_reset_ids() -> None:
    from apps.core.context import task_id_var

    seen: dict[str, Any] = {}

    @shared_task(name="tests.capture_ctx", base=BaseTask)
    def capture() -> None:
        seen["task_id"] = task_id_var.get()

    capture.apply(task_id="task-123")
    assert seen["task_id"] == "task-123"
    assert task_id_var.get() is None


def test_request_id_propagated_to_published_headers() -> None:
    from apps.core.context import request_id_var
    from apps.core.signals import _propagate_request_id

    headers: dict[str, Any] = {}
    token = request_id_var.set("req_PROPAGATE1")
    try:
        _propagate_request_id(headers=headers)
    finally:
        request_id_var.reset(token)
    assert headers["mhrs_request_id"] == "req_PROPAGATE1"


# ---------------------------------------------------------------- management commands
def test_send_test_email_command() -> None:
    out = StringIO()
    call_command("send_test_email", "--to", "qa@mhrs.local", stdout=out)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["qa@mhrs.local"]
    assert "MUDHOTECH HR RECRUITING SYSTEM" in mail.outbox[0].subject


def test_celery_ping_command() -> None:
    out = StringIO()
    fake = mock.Mock()
    fake.get.return_value = "pong"
    with mock.patch("config.celery.app.send_task", return_value=fake):
        call_command("celery_ping", stdout=out)
    assert "pong" in out.getvalue()


def test_celery_ping_command_timeout() -> None:
    from django.core.management.base import CommandError

    fake = mock.Mock()
    fake.get.side_effect = TimeoutError("no worker")
    with mock.patch("config.celery.app.send_task", return_value=fake), pytest.raises(CommandError):
        call_command("celery_ping", "--timeout", "0.1", stdout=StringIO())
