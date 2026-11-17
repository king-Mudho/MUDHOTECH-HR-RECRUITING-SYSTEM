"""Export bundle for access/export requests (P09-T03, EC-PRV-03)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import timedelta
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import ApplicationDocument, Status
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AccessLog, AuditEvent
from apps.core import storage
from apps.core.time import now
from apps.documents.models import Document, ScanStatus
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy import export, rights
from apps.privacy.models import RightsRequest

pytestmark = pytest.mark.django_db
PASSWORD = "lantern-orchard-velvet-27"


@pytest.fixture
def world(s3: Any) -> Any:
    team = make_org_with_team()
    candidate = UserFactory(verified=True, first_name="Rudo", last_name="Moyo")
    candidate.set_password(PASSWORD)
    candidate.save()
    app = make_application(
        published_job(organisation=team.org), candidate, status=Status.UNDER_REVIEW
    )
    doc = Document.objects.create(
        owner_user=candidate,
        purpose="cv",
        original_filename="rudo_cv.pdf",
        size_bytes=9,
        storage_key=f"cv/{app.pk}/rudo_cv.pdf",
        bucket="documents",
        scan_status=ScanStatus.CLEAN,
    )
    storage.put_bytes("documents", doc.storage_key, b"%PDF-1.4\n", "application/pdf")
    ApplicationDocument.objects.create(
        organisation=team.org, application=app, document=doc, role="cv", required_doc_key="cv"
    )
    other = make_application(
        published_job(organisation=team.org), UserFactory(), status=Status.UNDER_REVIEW
    )
    return team, candidate, app, other


def confirm(candidate: Any, act: Any) -> list[RightsRequest]:
    n = Notification.objects.filter(recipient_user=candidate, key="rights_request_confirm").latest(
        "created_at"
    )
    token = re.search(r"token=([\w-]+)", n.payload["confirm_url"]).group(1)  # type: ignore[union-attr]
    return act(rights.confirm, candidate, token)


@pytest.fixture
def act(django_capture_on_commit_callbacks: Any) -> Any:
    def run(fn: Any, *args: Any, **kwargs: Any) -> Any:
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)

    return run


def test_export_is_built_on_confirmation_and_downloadable(world: Any, act: Any) -> None:
    team, candidate, app, other = world
    (row,) = rights.create(
        candidate,
        type="export",
        password=PASSWORD,
        scope="organisation",
        organisation_id=team.org.pk,
    )
    confirm(candidate, act)
    row.refresh_from_db()
    assert row.export_document_id and row.export_expires_at > now() + timedelta(hours=23)
    archive = zipfile.ZipFile(io.BytesIO(storage.get_bytes("exports", export.export_key(row))))
    names = set(archive.namelist())
    assert {"data.json", "summary.pdf"} <= names
    assert any(n.startswith("documents/") and n.endswith("rudo_cv.pdf") for n in names)
    data = json.loads(archive.read("data.json"))
    assert data["account"]["first_name"] == "Rudo"
    assert [a["reference"] for a in data["applications"]] == [app.reference]  # not someone else's
    assert str(other.pk) not in json.dumps(data)
    assert archive.read("summary.pdf").startswith(b"%PDF")

    c = APIClient()
    c.force_login(candidate)
    res = c.get(f"/api/v1/privacy/requests/{row.pk}/export/")
    assert res.status_code == 200 and res.json()["url"].startswith("http")
    assert AuditEvent.objects.filter(action="privacy.export_downloaded").exists()
    assert AccessLog.objects.filter(user=candidate, action="export_download").exists()
    stranger = APIClient()
    stranger.force_login(UserFactory())
    assert stranger.get(f"/api/v1/privacy/requests/{row.pk}/export/").status_code == 404

    # the handler can complete it now; an expired link is refused
    rights.act(team.org.pk, team.admin, row.pk, action="complete", resolution="Export sent to you.")
    RightsRequest.objects.filter(pk=row.pk).update(export_expires_at=now() - timedelta(minutes=1))
    assert c.get(f"/api/v1/privacy/requests/{row.pk}/export/").status_code == 409


def test_cannot_complete_before_the_export_exists(world: Any) -> None:
    from apps.core.exceptions import ConflictError

    team, candidate, _, _ = world
    (row,) = rights.create(
        candidate,
        type="access",
        password=PASSWORD,
        scope="organisation",
        organisation_id=team.org.pk,
    )
    RightsRequest.objects.filter(pk=row.pk).update(status="received", verify_token_hash="")
    with pytest.raises(ConflictError) as exc:
        rights.act(team.org.pk, team.admin, row.pk, action="complete", resolution="Done already")
    assert exc.value.code == "conflict.export_not_ready"


def test_ai_evaluations_are_included_and_labelled_as_suggestions(world: Any, act: Any) -> None:
    """Evaluations are included as AI-assisted suggestions (right of access)."""
    team, candidate, app, _ = world
    from apps.screening.models import Evaluation

    Evaluation.objects.create(
        organisation=team.org,
        application=app,
        job_version=app.job_version,
        version=1,
        total_score=72,
        coverage=1,
        band="review_needed",
        input_hash="h",
        engine_version="x",
    )
    (row,) = rights.create(candidate, type="access", password=PASSWORD, scope="all")[:1]
    confirm(candidate, act)
    row.refresh_from_db()
    data = json.loads(
        zipfile.ZipFile(io.BytesIO(storage.get_bytes("exports", export.export_key(row)))).read(
            "data.json"
        )
    )
    (ev,) = data["applications"][0]["evaluations"]
    assert ev["band"] == "review_needed" and "not a decision" in ev["note"]
