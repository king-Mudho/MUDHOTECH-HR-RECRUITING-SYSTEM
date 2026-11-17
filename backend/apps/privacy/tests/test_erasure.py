"""Deletion and anonymisation (P09-T04; EC-PRV-01/02/05, EC-ACC-13)."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import (
    Application,
    ApplicationDocument,
    ApplicationNote,
    ApplicationStatusEvent,
    Status,
)
from apps.applications.tests.factories import make_application, published_job
from apps.audit.models import AuditEvent
from apps.core import storage
from apps.documents.models import Document, ScanStatus
from apps.messaging.models import Message, MessageThread
from apps.notifications.models import Notification
from apps.organisations.tests.factories import make_org_with_team
from apps.privacy import erasure, rights, services
from apps.privacy.models import ConsentRecord, RightsRequest
from apps.questionnaires.models import QuestionResponse

pytestmark = pytest.mark.django_db
PASSWORD = "lantern-orchard-velvet-27"
EMAIL = "rudo.moyo@example.test"


def doc_for(app: Any, user: Any, name: str) -> Document:
    doc = Document.objects.create(
        owner_user=user,
        purpose="cv",
        original_filename=name,
        size_bytes=4,
        storage_key=f"cv/{app.pk}/{name}",
        bucket="documents",
        scan_status=ScanStatus.CLEAN,
    )
    storage.put_bytes("documents", doc.storage_key, b"data", "application/pdf")
    ApplicationDocument.objects.create(
        organisation_id=app.organisation_id, application=app, document=doc, role="cv"
    )
    return doc


@pytest.fixture
def world(s3: Any) -> Any:
    a, b = make_org_with_team(), make_org_with_team()
    user = UserFactory(verified=True, email=EMAIL, first_name="Rudo", last_name="Moyo")
    user.set_password(PASSWORD)
    user.save()
    snap = {"first_name": "Rudo", "last_name": "Moyo", "email": EMAIL}
    app_a = make_application(published_job(organisation=a.org), user, status=Status.UNDER_REVIEW)
    app_b = make_application(published_job(organisation=b.org), user, status=Status.NOT_SELECTED)
    for app in (app_a, app_b):
        Application.objects.unscoped().filter(pk=app.pk).update(candidate_profile_snapshot=snap)
    doc_a = doc_for(app_a, user, "Rudo_Moyo_CV.pdf")
    doc_b = doc_for(app_b, user, "Rudo_Moyo_CV_v2.pdf")
    thread = MessageThread.objects.create(organisation=a.org, application=app_a)
    Message.objects.create(
        organisation=a.org,
        thread=thread,
        sender_user=user,
        sender_role="candidate",
        body="Hi, Rudo here",
    )
    ApplicationNote.objects.create(
        organisation=a.org, application=app_a, author=a.recruiter, body="Rudo knows Django"
    )
    ConsentRecord.objects.create(
        user=user,
        organisation=a.org,
        purpose="application_processing",
        notice_version="v1",
        granted=True,
        granted_at=app_a.created_at,
    )
    return a, b, user, app_a, app_b, doc_a, doc_b


def test_org_scoped_erasure_withdraws_and_removes_pii(world: Any) -> None:
    a, _b, user, app_a, app_b, doc_a, doc_b = world
    key_a, key_b = doc_a.storage_key, doc_b.storage_key
    counts = erasure.erase(user, a.org.pk, actor=a.admin)
    assert counts["withdrawn"] == 1 and counts["applications"] == 1 and counts["files"] == 1
    app_a.refresh_from_db()
    assert app_a.status == "withdrawn" and app_a.candidate_profile_snapshot == {"erased": True}
    event = (
        ApplicationStatusEvent.objects.for_org(a.org)
        .filter(application=app_a, to_status="withdrawn")
        .get()
    )
    assert event.actor_id == user.pk  # withdrawn as the candidate (EC-PRV-02)
    assert Message.objects.for_org(a.org).get().body == "[erased]"
    assert ApplicationNote.objects.for_org(a.org).get().body == "[erased]"
    doc_a.refresh_from_db()
    assert doc_a.deleted_at and doc_a.original_filename == "[erased]"
    assert storage.head_object("documents", key_a) is None  # gone from storage
    # the other employer's data is untouched
    app_b.refresh_from_db()
    assert app_b.candidate_profile_snapshot["first_name"] == "Rudo"
    assert storage.get_bytes("documents", key_b) == b"data"
    event = AuditEvent.objects.get(action="privacy.erased")
    assert "Rudo" not in str(event.after) and EMAIL not in str(event.after)


def test_account_erasure_leaves_no_pii(world: Any) -> None:
    _a, _b, user, *_ = world
    erasure.erase(user)
    user.refresh_from_db()
    assert user.email.endswith("@erased.invalid") and not user.is_active
    assert not user.has_usable_password()
    assert erasure.residual_pii(user.pk, [EMAIL, "Rudo", "Moyo"]) == {}
    call_command("verify_erasure", str(user.pk), "--value", EMAIL, "--value", "Moyo")
    # consent records stay as proof, linked to the anonymous account
    assert ConsentRecord.objects.filter(user=user).count() == 1


def test_verify_erasure_fails_when_pii_remains(world: Any) -> None:
    _, _, user, *_ = world
    with pytest.raises(CommandError):
        call_command("verify_erasure", str(user.pk), "--value", EMAIL)


def test_legal_hold_blocks_erasure(world: Any) -> None:
    a, _, user, app_a, *_ = world
    services.place_hold(
        a.org.pk,
        a.admin,
        target_type="application",
        target_id=app_a.pk,
        reason="Tribunal case 1/26",
    )
    with pytest.raises(erasure.LegalHoldError):
        erasure.erase(user, a.org.pk)
    app_a.refresh_from_db()
    assert app_a.candidate_profile_snapshot["first_name"] == "Rudo"  # nothing touched


def test_deletion_request_completes_by_erasing_or_waits_for_hold(world: Any) -> None:
    a, _, user, app_a, *_ = world
    (row,) = rights.create(
        user, type="deletion", password=PASSWORD, scope="organisation", organisation_id=a.org.pk
    )
    n = Notification.objects.filter(recipient_user=user, key="rights_request_confirm").latest(
        "created_at"
    )
    rights.confirm(user, re.search(r"token=([\w-]+)", n.payload["confirm_url"]).group(1))  # type: ignore[union-attr]
    hold = services.place_hold(
        a.org.pk, a.admin, target_type="candidate", target_id=user.pk, reason="Pending dispute"
    )
    held = rights.act(a.org.pk, a.admin, row.pk, action="complete", resolution="Deleted as asked.")
    assert held.status == "on_hold"  # EC-PRV-01: recorded, hold explained, done after release
    services.release_hold(a.org.pk, a.admin, hold.pk)
    rights.act(a.org.pk, a.admin, row.pk, action="start")  # back in progress after release
    done = rights.act(a.org.pk, a.admin, row.pk, action="complete", resolution="Deleted as asked.")
    assert done.status == "completed"
    app_a.refresh_from_db()
    assert app_a.candidate_profile_snapshot == {"erased": True}


def test_platform_deletion_erases_the_account(world: Any) -> None:
    _, _, user, *_ = world
    admin = UserFactory(verified=True, platform_role=PlatformRole.PLATFORM_ADMIN)
    (row,) = rights.create(user, type="deletion", password=PASSWORD, scope="platform")
    n = Notification.objects.filter(recipient_user=user, key="rights_request_confirm").latest(
        "created_at"
    )
    rights.confirm(user, re.search(r"token=([\w-]+)", n.payload["confirm_url"]).group(1))  # type: ignore[union-attr]
    rights.act(None, admin, row.pk, action="complete", resolution="Your account was deleted.")
    user.refresh_from_db()
    assert not user.is_active and user.email.endswith("@erased.invalid")
    assert RightsRequest.objects.get(pk=row.pk).status == "completed"
    assert (
        QuestionResponse.objects.unscoped()
        .filter(application__candidate_user=user)
        .exclude(value=None)
        .count()
        == 0
    )
