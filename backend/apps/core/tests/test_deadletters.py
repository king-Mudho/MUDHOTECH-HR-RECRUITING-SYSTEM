"""EC-OPS-07: dead letters can be retried or resolved by an operator, with an audit trail."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import site
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.core import deadletters
from apps.core.models import DeadLetter

pytestmark = pytest.mark.django_db


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[Any], dict[str, Any]]]:
    calls: list[tuple[str, list[Any], dict[str, Any]]] = []
    monkeypatch.setattr(deadletters, "_send", lambda n, a, k: calls.append((n, a, k)))
    return calls


def test_retry_requeues_after_commit_and_audits(
    sent: list[Any], django_capture_on_commit_callbacks: Any
) -> None:
    op = UserFactory()
    dl = DeadLetter.objects.create(
        task_name="apps.documents.tasks.scan_document", args=["abc"], kwargs={"x": 1}, error="boom"
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert deadletters.retry(dl, op) is True
    assert sent == [("apps.documents.tasks.scan_document", ["abc"], {"x": 1})]
    dl.refresh_from_db()
    assert dl.resolved_at and dl.resolved_by == op
    assert AuditEvent.objects.filter(action="dead_letter.retried").count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert deadletters.retry(dl, op) is False  # never queued twice
    assert len(sent) == 1


def test_resolve_without_retry(sent: list[Any]) -> None:
    dl = DeadLetter.objects.create(task_name="t", error="e")
    assert deadletters.resolve(dl, UserFactory(), "object deleted") is True
    assert sent == []
    event = AuditEvent.objects.get(action="dead_letter.resolved")
    assert event.reason == "object deleted"


def test_admin_actions(sent: list[Any], django_capture_on_commit_callbacks: Any) -> None:
    admin_obj = site._registry[DeadLetter]
    a = DeadLetter.objects.create(task_name="t.a", error="e")
    b = DeadLetter.objects.create(task_name="t.b", error="e")
    request = RequestFactory().post("/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    request.session = {}  # type: ignore[assignment]
    request._messages = FallbackStorage(request)  # type: ignore[attr-defined]
    with django_capture_on_commit_callbacks(execute=True):
        admin_obj.retry_selected(request, DeadLetter.objects.filter(pk=a.pk))
    admin_obj.resolve_selected(request, DeadLetter.objects.filter(pk=b.pk))
    assert [s[0] for s in sent] == ["t.a"]
    assert DeadLetter.objects.filter(resolved_at__isnull=True).count() == 0
