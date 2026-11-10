"""CV library and candidate timeline (P04-T13)."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import ApplicationDocument, Status
from apps.applications.services import transition
from apps.applications.tests.factories import make_application
from apps.documents.models import Document, ScanStatus

pytestmark = pytest.mark.django_db


def cv(user: Any, **kw: Any) -> Document:
    return Document.objects.create(
        owner_user=user,
        purpose="cv",
        original_filename=kw.pop("name", "cv.pdf"),
        size_bytes=100,
        storage_key="k",
        scan_status=kw.pop("scan", ScanStatus.CLEAN),
        **kw,
    )


@pytest.fixture
def user() -> Any:
    return UserFactory()


@pytest.fixture
def client(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def test_library_lists_own_cvs_and_sets_default(client: APIClient, user: Any) -> None:
    a, b = cv(user, name="a.pdf"), cv(user, name="b.pdf")
    cv(UserFactory(), name="someone-else.pdf")
    Document.objects.create(
        owner_user=user,
        purpose="supporting",
        original_filename="cert.pdf",
        size_bytes=1,
        storage_key="k",
    )
    names = [r["original_filename"] for r in client.get("/api/v1/candidate/resumes/").json()]
    assert sorted(names) == ["a.pdf", "b.pdf"]
    res = client.post(f"/api/v1/candidate/resumes/{b.pk}/set-default/")
    assert res.status_code == 200 and "resume" not in res.json()["missing"]
    rows = {
        r["original_filename"]: r["is_default"]
        for r in client.get("/api/v1/candidate/resumes/").json()
    }
    assert rows == {"a.pdf": False, "b.pdf": True}
    bad = cv(user, scan=ScanStatus.INFECTED)
    assert client.post(f"/api/v1/candidate/resumes/{bad.pk}/set-default/").status_code == 400
    other = cv(UserFactory())
    assert client.post(f"/api/v1/candidate/resumes/{other.pk}/set-default/").status_code == 404
    assert a.pk  # unused-variable guard


def test_remove_cv_rules(client: APIClient, user: Any) -> None:
    free, used = cv(user, name="free.pdf"), cv(user, name="used.pdf")
    client.post(f"/api/v1/candidate/resumes/{free.pk}/set-default/")
    app = make_application(user=user, status=Status.SUBMITTED)
    ApplicationDocument.objects.create(
        organisation_id=app.organisation_id, application=app, document=used, role="cv"
    )
    assert client.delete(f"/api/v1/candidate/resumes/{used.pk}/").status_code == 409
    assert client.delete(f"/api/v1/candidate/resumes/{free.pk}/").status_code == 204
    free.refresh_from_db()
    assert free.deleted_at is not None
    profile = client.get("/api/v1/candidate/profile/").json()
    assert "resume" in profile["missing"]  # default cleared


def test_timeline_hides_internal_steps_and_reasons(client: APIClient, user: Any) -> None:
    from apps.applications.tests.factories import published_job
    from apps.organisations.tests.factories import make_org_with_team

    team = make_org_with_team()
    app = make_application(published_job(organisation=team.org), user, status=Status.SUBMITTED)
    transition(app, Status.PROCESSING, actor_type="system")
    transition(app, Status.UNDER_REVIEW, actor_type="system")
    transition(app, Status.ON_HOLD, actor=team.recruiter, reason="Internal: waiting for budget")
    transition(app, Status.WITHDRAWN, actor=user, reason="Took another role")
    rows = client.get(f"/api/v1/applications/{app.pk}/timeline/").json()
    assert [r["status"] for r in rows] == ["submitted", "under_review", "withdrawn"]
    assert rows[-1]["note"] == "Took another role"
    assert "budget" not in str(rows)
    other = APIClient()
    other.force_login(UserFactory())
    assert other.get(f"/api/v1/applications/{app.pk}/timeline/").status_code == 404
