"""P14-T03: entitlements - trial on creation, plan limits on publishing, invitations, screening
runs and staff uploads; read-only subscriptions; candidates never blocked (EC-BIL-03)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Application, Status
from apps.applications.tests.factories import make_application, published_job
from apps.applications.tests.test_submit import ready_draft, submit
from apps.billing import entitlements
from apps.billing.models import Plan, Subscription, SubscriptionStatus
from apps.core.exceptions import DomainError
from apps.core.time import now
from apps.documents import services as documents
from apps.jobs import services as jobs
from apps.jobs.models import Job, JobStatus
from apps.jobs.tests.test_services import approved_job
from apps.organisations import services as orgs
from apps.organisations.models import OrganisationPolicy
from apps.organisations.tests.factories import make_org_with_team
from apps.screening import services as screening

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enforce(settings: Any) -> None:
    settings.BILLING_ENFORCE = True


@pytest.fixture
def team() -> Any:
    t = make_org_with_team()
    t.org.verified_at = now()
    t.org.save(update_fields=["verified_at"])
    OrganisationPolicy.objects.filter(organisation=t.org).update(
        privacy_notice="We process your application data to assess suitability for the role."
    )
    return t


def limits(org: Any, **values: int | None) -> Subscription:
    sub = entitlements.subscription_for(org.pk)
    plan = Plan.objects.create(
        code=f"test-{uuid.uuid4().hex[:12]}", name="Test plan", limits=values
    )
    Subscription.objects.for_org(org.pk).filter(pk=sub.pk).update(
        plan=plan, status=SubscriptionStatus.ACTIVE
    )
    return Subscription.objects.for_org(org.pk).get()


def test_new_organisation_starts_a_30_day_trial() -> None:
    user = UserFactory()
    org = orgs.create_organisation(
        user=user, data={"name": "Trial Test Ltd", "industry": "IT", "city": "Harare"}
    )
    sub = Subscription.objects.for_org(org.pk).get()
    assert sub.plan.code == "trial" and sub.status == SubscriptionStatus.TRIALING
    assert timedelta(days=29) < sub.trial_ends_at - now() <= timedelta(days=30)


def test_publish_is_limited_but_published_jobs_keep_taking_applications(team: Any) -> None:
    limits(team.org, active_vacancies=1)
    live = published_job(organisation=team.org)  # already live (no questions to answer)
    blocked = approved_job(team)
    with pytest.raises(DomainError) as err:
        jobs.publish(blocked, actor=team.hr_manager)
    assert err.value.code == "plan_limit_reached"
    assert err.value.details["metric"] == "active_vacancies" and err.value.details["limit"] == 1
    with pytest.raises(DomainError):
        jobs.schedule(blocked, actor=team.hr_manager, publish_at=now() + timedelta(days=1))
    # EC-BIL-03: candidates still apply and submit to the vacancy that is already live
    user = UserFactory()
    draft = ready_draft(live, user)
    client = APIClient()
    client.force_login(user)
    assert submit(client, draft).status_code == 201
    # a scheduled publish that no longer fits is cancelled, not forced through
    limits(team.org, active_vacancies=5)
    jobs.schedule(blocked, actor=team.hr_manager, publish_at=now() + timedelta(minutes=5))
    limits(team.org, active_vacancies=1)
    Job.objects.for_org(team.org).filter(pk=blocked.pk).update(publish_at=now() - timedelta(1))
    assert jobs.publish_scheduled(blocked) is False
    blocked.refresh_from_db()
    assert blocked.status == JobStatus.APPROVED


def test_seats_limit_invitations(team: Any) -> None:
    limits(team.org, seats=7)  # the team has 6 active members
    orgs.invite_member(org=team.org, actor=team.admin, email="new@example.test", role="recruiter")
    # re-sending to the same address replaces the open invitation: still allowed at the limit
    orgs.invite_member(org=team.org, actor=team.admin, email="new@example.test", role="recruiter")
    with pytest.raises(DomainError) as err:
        orgs.invite_member(
            org=team.org, actor=team.admin, email="other@example.test", role="recruiter"
        )
    assert err.value.code == "plan_limit_reached" and err.value.details["metric"] == "seats"


def test_screening_runs_and_automatic_screening(team: Any) -> None:
    from apps.organisations.models import Membership
    from apps.screening.runs import start_run

    job = published_job(organisation=team.org)
    for _ in range(3):
        make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    limits(team.org, ai_evaluations_month=2)
    hr = Membership.objects.for_org(team.org).get(user=team.hr_manager)
    with pytest.raises(DomainError) as err:
        start_run(hr, team.hr_manager, job.pk, scope="all", reason="Re-check everyone")
    assert err.value.details["metric"] == "ai_evaluations_month"
    # automatic screening after a submission: never blocks - a person reviews instead
    limits(team.org, ai_evaluations_month=0)
    app = make_application(job, UserFactory(), status=Status.PROCESSING)
    assert screening.evaluate_application(app.pk) is None
    app.refresh_from_db()
    assert app.ai_band == screening.MANUAL_BAND and app.status != Status.PROCESSING_ERROR


def test_staff_uploads_count_against_storage_but_candidate_documents_never(
    team: Any, s3: Any
) -> None:
    limits(team.org, storage_gb=0)
    staff = team.hr_manager
    with pytest.raises(DomainError) as err:
        documents.create_session(
            staff,
            purpose="offer_letter",
            filename="letter.pdf",
            mime="application/pdf",
            size=1000,
            organisation=team.org,
        )
    assert err.value.details["metric"] == "storage_gb"
    pdf = SimpleUploadedFile("cv.pdf", b"%PDF-1.4 cv", content_type="application/pdf")
    doc = documents.direct_upload(staff, purpose="cv", uploaded=pdf, organisation=team.org)
    assert doc.pk  # assisted application CV: a candidate document


def test_read_only_subscription_blocks_staff_actions_not_candidates(team: Any) -> None:
    live = published_job(organisation=team.org)
    sub = entitlements.subscription_for(team.org.pk)
    Subscription.objects.for_org(team.org).filter(pk=sub.pk).update(
        status=SubscriptionStatus.READ_ONLY
    )
    with pytest.raises(DomainError) as err:
        jobs.publish(approved_job(team), actor=team.hr_manager)
    assert err.value.code == "billing_read_only"
    user = UserFactory()
    client = APIClient()
    client.force_login(user)
    assert submit(client, ready_draft(live, user)).status_code == 201
    assert Application.objects.for_org(team.org).filter(status=Status.SUBMITTED).exists()


def test_enforcement_can_be_switched_off(team: Any, settings: Any) -> None:
    settings.BILLING_ENFORCE = False
    limits(team.org, active_vacancies=0)
    assert jobs.publish(approved_job(team), actor=team.hr_manager).status == JobStatus.PUBLISHED
