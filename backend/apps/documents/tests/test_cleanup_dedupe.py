"""Upload housekeeping (EC-APP-08) and per-user de-duplication (EC-DOC-25) - P04-T04."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest import mock

import pytest
from django.conf import settings

from apps.accounts.tests.factories import UserFactory
from apps.core.exceptions import DomainError
from apps.core.time import now
from apps.documents import cleanup, pipeline
from apps.documents.models import Document, ScanStatus, UploadSession
from apps.documents.services import complete_session, create_session
from apps.documents.tests.test_scan_pipeline import make_pdf

pytestmark = pytest.mark.django_db

Q = "mhrs-uploads-quarantine"


def keys(s3: Any, bucket: str = Q) -> set[str]:
    return {o["Key"] for o in s3.list_objects_v2(Bucket=bucket).get("Contents", [])}


def later(hours: int = 25) -> Any:
    return mock.patch("apps.documents.cleanup.now", return_value=now() + timedelta(hours=hours))


def test_beat_schedule_runs_cleanup_hourly() -> None:
    tasks = {e["task"] for e in settings.CELERY_BEAT_SCHEDULE.values()}
    assert "apps.documents.tasks.cleanup_uploads" in tasks


def test_unconfirmed_upload_is_expired_and_removed(s3: Any) -> None:
    """EC-APP-08: the browser uploaded but never called complete."""
    user = UserFactory()
    session, _ = create_session(
        user, purpose="cv", filename="cv.pdf", mime="application/pdf", size=10
    )
    s3.put_object(Bucket=Q, Key=session.object_key, Body=make_pdf())
    assert cleanup.run().orphans_deleted == 0  # still fresh and live
    with later():
        result = cleanup.run()
    assert result.sessions_expired == 1 and result.orphans_deleted == 1
    assert UploadSession.objects.get(pk=session.pk).status == "expired"
    assert keys(s3) == set()
    with pytest.raises(DomainError) as exc:  # an expired session can no longer be completed
        complete_session(user, session.pk)
    assert exc.value.code == "conflict.upload_closed"


def test_pending_documents_and_live_sessions_are_kept(s3: Any) -> None:
    user = UserFactory()
    session, _ = create_session(
        user, purpose="cv", filename="cv.pdf", mime="application/pdf", size=10
    )
    s3.put_object(Bucket=Q, Key=session.object_key, Body=make_pdf())
    doc = complete_session(user, session.pk)  # scan deferred (on_commit not run) -> pending
    with later():
        assert cleanup.run().orphans_deleted == 0
    assert doc.storage_key in keys(s3)


def test_rejected_files_are_purged_after_grace_but_rows_kept(s3: Any) -> None:
    user = UserFactory()
    doc = Document.objects.create(
        owner_user=user,
        purpose="cv",
        original_filename="bad.pdf",
        size_bytes=3,
        storage_key="cv/x/bad.pdf",
        scan_status=ScanStatus.INFECTED,
        rejected_reason="malware",
    )
    s3.put_object(Bucket=Q, Key=doc.storage_key, Body=b"bad")
    assert cleanup.run().rejected_purged == 0
    with later():
        assert cleanup.run().rejected_purged == 1
    doc.refresh_from_db()
    assert doc.deleted_at is not None and doc.scan_status == ScanStatus.INFECTED
    assert keys(s3) == set()
    with later():
        assert cleanup.run().rejected_purged == 0  # idempotent


def test_same_file_twice_is_deduplicated_per_user(s3: Any) -> None:
    """EC-DOC-25: identical bytes for the same user and purpose reuse the accepted file."""
    user = UserFactory()
    data = make_pdf(2)

    def put_and_scan(u: Any) -> Document:
        session, _ = create_session(
            u, purpose="cv", filename="cv.pdf", mime="application/pdf", size=len(data)
        )
        s3.put_object(Bucket=Q, Key=session.object_key, Body=data)
        doc = complete_session(u, session.pk)
        pipeline.scan_document(doc.pk)
        doc.refresh_from_db()
        return doc

    first = put_and_scan(user)
    second = put_and_scan(user)
    assert first.scan_status == second.scan_status == ScanStatus.CLEAN
    assert second.duplicate_of_id == first.pk and second.storage_key == first.storage_key
    assert second.page_count == 2 and second.sha256 == first.sha256
    assert keys(s3) == set()  # quarantine copy of the duplicate removed
    assert len(keys(s3, "mhrs-documents")) == 1  # stored once
    other = put_and_scan(UserFactory())  # another user's identical file is independent
    assert other.duplicate_of_id is None and other.storage_key != first.storage_key
