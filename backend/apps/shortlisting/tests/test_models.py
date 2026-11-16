"""Shortlist models and decision reasons (P08-T01)."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.applications.models import DecisionReason, Status
from apps.applications.tests.factories import make_application, published_job
from apps.core.time import now
from apps.organisations.tests.factories import make_org_with_team
from apps.shortlisting.models import Shortlist, ShortlistEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup() -> Any:
    team = make_org_with_team()
    job = published_job(organisation=team.org, title="Software Developer")
    app = make_application(job, UserFactory(), status=Status.UNDER_REVIEW)
    shortlist = Shortlist.objects.create(
        organisation=team.org,
        job=job,
        job_version=job.published_version,
        desired_size=10,
        proposed_by=team.recruiter,
    )
    return team, job, app, shortlist


def test_reasons_are_seeded_for_every_decision_kind() -> None:
    codes = {
        (r.applies_to, r.code) for r in DecisionReason.objects.filter(organisation__isnull=True)
    }
    for item in (
        ("not_selected", "essential_not_met"),
        ("not_selected", "less_relevant_experience"),
        ("not_selected", "eligibility_not_met"),
        ("hold", "pending_verification"),
        ("override", "evidence_review_differs"),
        ("shortlist", "meets_essential"),
    ):
        assert item in codes
    label = DecisionReason.objects.get(organisation=None, code="essential_not_met").label
    assert label == "Essential criterion not evidenced after review"
    every = " ".join(DecisionReason.objects.values_list("label", flat=True)).lower()
    assert "rejected" not in every


def test_only_one_open_shortlist_per_vacancy(setup: Any) -> None:
    team, job, _, shortlist = setup
    with pytest.raises(IntegrityError), transaction.atomic():
        Shortlist.objects.create(
            organisation=team.org,
            job=job,
            job_version=job.published_version,
            proposed_by=team.recruiter,
            status=Shortlist.Status.PENDING_APPROVAL,
        )
    shortlist.status = Shortlist.Status.APPROVED
    shortlist.save()
    again = Shortlist.objects.create(
        organisation=team.org,
        job=job,
        job_version=job.published_version,
        proposed_by=team.recruiter,
    )
    assert again.is_open and not Shortlist.objects.for_org(team.org).get(pk=shortlist.pk).is_open


def test_entries_start_as_suggestions_and_decisions_need_a_person(setup: Any) -> None:
    team, _, app, shortlist = setup
    entry = ShortlistEntry.objects.create(
        organisation=team.org, shortlist=shortlist, application=app, suggestion="shortlist"
    )
    assert entry.decision == ShortlistEntry.Decision.UNDECIDED  # a suggestion is not a decision
    with pytest.raises(IntegrityError), transaction.atomic():
        ShortlistEntry.objects.filter(pk=entry.pk).update(decision="shortlist")  # no actor
    with pytest.raises(IntegrityError), transaction.atomic():
        ShortlistEntry.objects.filter(pk=entry.pk).update(
            decision="not_selected", decided_by=team.hr_manager, decided_at=now()
        )  # not selected without a reason
    ShortlistEntry.objects.filter(pk=entry.pk).update(
        decision="not_selected",
        reason_code="essential_not_met",
        decided_by=team.hr_manager,
        decided_at=now(),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ShortlistEntry.objects.create(organisation=team.org, shortlist=shortlist, application=app)


def test_tenant_scoping(setup: Any) -> None:
    team, _, _, shortlist = setup
    other = make_org_with_team()
    assert not Shortlist.objects.for_org(other.org).filter(pk=shortlist.pk).exists()
    assert Shortlist.objects.for_org(team.org).filter(pk=shortlist.pk).exists()
