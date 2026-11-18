"""Phase 09 exit criterion: rights-request lifecycle end to end through the API.

A candidate exports their data and then asks for deletion; the employer's admin handles both;
afterwards ``verify_erasure`` finds no personal data in the database or object storage.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, ApplicationDocument, Status
from apps.applications.tests.factories import make_application, published_job
from apps.core import storage
from apps.documents.models import Document, ScanStatus
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy import export
from apps.privacy.models import RightsRequest

pytestmark = pytest.mark.django_db
PASSWORD = "lantern-orchard-velvet-27"  # pragma: allowlist secret - synthetic test password
EMAIL = "tendai.chuma@example.test"


def client(user: Any, org: Any = None) -> APIClient:
    c = APIClient()
    c.force_login(user)
    if org is not None:
        c.credentials(HTTP_X_ORG_ID=str(org.pk))
    return c


def token_for(user: Any) -> str:
    n = Notification.objects.filter(recipient_user=user, key="rights_request_confirm").latest(
        "created_at"
    )
    match = re.search(r"token=([\w-]+)", n.payload["confirm_url"])
    assert match is not None
    return match.group(1)


def test_export_then_deletion_leaves_no_personal_data(
    s3: Any, django_capture_on_commit_callbacks: Any
) -> None:
    team = make_org_with_team()
    user = UserFactory(verified=True, email=EMAIL, first_name="Tendai", last_name="Chuma")
    user.set_password(PASSWORD)
    user.save()
    app = make_application(published_job(organisation=team.org), user, status=Status.UNDER_REVIEW)
    Application.objects.unscoped().filter(pk=app.pk).update(
        candidate_profile_snapshot={"first_name": "Tendai", "last_name": "Chuma", "email": EMAIL}
    )
    doc = Document.objects.create(
        owner_user=user,
        purpose="cv",
        original_filename="Tendai_Chuma_CV.pdf",
        size_bytes=9,
        storage_key=f"cv/{app.pk}/Tendai_Chuma_CV.pdf",
        bucket="documents",
        scan_status=ScanStatus.CLEAN,
    )
    storage.put_bytes("documents", doc.storage_key, b"%PDF-1.4\n", "application/pdf")
    ApplicationDocument.objects.create(
        organisation=team.org, application=app, document=doc, role="cv", required_doc_key="cv"
    )
    me, hr = client(user), client(team.admin, team.org)
    base = {"scope": "organisation", "organisation_id": str(team.org.pk), "password": PASSWORD}

    # 1. export: wrong password refused, then request -> email confirmation -> bundle -> download
    wrong = {**base, "type": "export", "password": "nope"}  # pragma: allowlist secret
    assert me.post("/api/v1/privacy/requests/", wrong, format="json").status_code in (400, 403)
    created = me.post("/api/v1/privacy/requests/", {**base, "type": "export"}, format="json")
    assert created.status_code == 201
    export_id = created.json()[0]["id"]
    with django_capture_on_commit_callbacks(execute=True):
        res = me.post(
            "/api/v1/privacy/requests/confirm/", {"token": token_for(user)}, format="json"
        )
    assert res.status_code == 200
    row = RightsRequest.objects.get(pk=export_id)
    bundle = zipfile.ZipFile(io.BytesIO(storage.get_bytes("exports", export.export_key(row))))
    assert "data.json" in bundle.namelist() and b"Tendai" in bundle.read("data.json")
    assert me.get(f"/api/v1/privacy/requests/{export_id}/export/").status_code == 200
    done = hr.post(
        f"/api/v1/hr/privacy/requests/{export_id}/action/",
        {"action": "complete", "resolution": "Your export is ready to download."},
        format="json",
    )
    assert done.status_code == 200 and done.json()["status"] == "completed"

    # 2. deletion: request -> confirm -> the employer admin completes it, which erases
    created = me.post("/api/v1/privacy/requests/", {**base, "type": "deletion"}, format="json")
    deletion_id = created.json()[0]["id"]
    with django_capture_on_commit_callbacks(execute=True):
        me.post("/api/v1/privacy/requests/confirm/", {"token": token_for(user)}, format="json")
    with django_capture_on_commit_callbacks(execute=True):
        done = hr.post(
            f"/api/v1/hr/privacy/requests/{deletion_id}/action/",
            {"action": "complete", "resolution": "Your data has been deleted."},
            format="json",
        )
    assert done.status_code == 200 and done.json()["status"] == "completed"

    # the employer's records and files are gone; the platform account itself still exists
    app.refresh_from_db()
    assert app.candidate_profile_snapshot == {"erased": True}
    assert storage.head_object("documents", doc.storage_key) is None

    # 3. account deletion: handled by a platform admin, erases the account itself
    created = me.post(
        "/api/v1/privacy/requests/",
        {"type": "deletion", "scope": "platform", "password": PASSWORD},
        format="json",
    )
    account_id = created.json()[0]["id"]
    with django_capture_on_commit_callbacks(execute=True):
        me.post("/api/v1/privacy/requests/confirm/", {"token": token_for(user)}, format="json")
    platform = client(UserFactory(verified=True, platform_role=PlatformRole.PLATFORM_ADMIN))
    with django_capture_on_commit_callbacks(execute=True):
        done = platform.post(
            f"/api/v1/platform/privacy/requests/{account_id}/action/",
            {"action": "complete", "resolution": "Your account was deleted."},
            format="json",
        )
    assert done.status_code == 200 and done.json()["status"] == "completed"

    # 4. verification script: no personal data left in the database or object storage
    call_command(
        "verify_erasure",
        str(user.pk),
        value=[EMAIL, "Tendai", "Chuma", "Tendai_Chuma_CV.pdf"],
        stdout=io.StringIO(),
    )
