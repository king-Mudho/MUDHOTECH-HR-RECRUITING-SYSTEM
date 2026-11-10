"""seed_demo (P03-T14): demo orgs, users per role and three published, complete vacancies."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.accounts.models import PlatformRole, User
from apps.jobs import services as jobs
from apps.jobs.models import Job, JobStatus
from apps.organisations.models import Membership, Organisation, Role
from apps.platform.demo_seed import seed
from apps.questionnaires.validation import validate_questions

pytestmark = pytest.mark.django_db

PASSWORD = "Synthetic-Demo-Seed-2026"


def test_seed_creates_orgs_users_and_published_jobs() -> None:
    result = seed(PASSWORD)
    assert result.organisations == ["MudhoTech Demo Ltd", "Acme Mining Zimbabwe"]
    assert len(result.users) == 13
    admin = User.objects.get(email="admin@mhrs-demo.test")
    assert admin.platform_role == PlatformRole.PLATFORM_ADMIN and admin.check_password(PASSWORD)

    for org in Organisation.objects.filter(name__in=result.organisations):
        assert org.status == Organisation.Status.ACTIVE and org.verified_at is not None
        roles = set(Membership.objects.for_org(org).values_list("role", flat=True))
        assert roles == set(Role.values)

    titles = set(Job.objects.unscoped().values_list("title", flat=True))
    assert titles == {"Software Developer", "Accountant", "Registered Nurse"}
    for job in Job.objects.unscoped().select_related("published_version", "organisation"):
        assert job.status == JobStatus.PUBLISHED
        v = job.published_version
        assert v is not None and v.status == "approved" and v.snapshot["criteria"]
        assert v.rubric.total_weight == 100 and v.rubric.status == "approved"
        assert v.criteria.filter(importance="essential").exists()
        assert all(c.justification for c in v.criteria.filter(importance="essential"))
        assert v.questionnaire.status == "approved" and v.questionnaire.questions.exists()
        assert jobs.readiness(job)["ready"]


def test_software_developer_follows_blueprint_appendix_a() -> None:
    seed(PASSWORD)
    job = Job.objects.unscoped().get(title="Software Developer")
    v = job.published_version
    assert v is not None
    essential = set(v.criteria.filter(importance="essential").values_list("title", flat=True))
    preferred = set(v.criteria.filter(importance="preferred").values_list("title", flat=True))
    assert {"Python", "SQL", "Git"} <= essential
    assert {"Django", "REST API design", "Cloud deployment"} <= preferred
    keys = list(v.questionnaire.questions.values_list("key", flat=True))
    assert keys[:3] == ["python-project", "api-design", "databases"]
    # Criteria link to the taxonomy where a skill exists (loaded on demand by the seed).
    python = v.criteria.get(title="Python")
    assert python.skill is not None and python.skill.canonical_name == "Python"


def test_seed_questions_are_valid_and_nurse_knockout_never_scores_salary() -> None:
    from apps.jobs.services import _question_dict

    seed(PASSWORD)
    for job in Job.objects.unscoped().select_related("published_version"):
        questions = job.published_version.questionnaire.questions.prefetch_related("options")  # type: ignore[union-attr]
        assert validate_questions([_question_dict(q) for q in questions]) == {}
    nurse = Job.objects.unscoped().get(title="Registered Nurse")
    q = nurse.published_version.questionnaire.questions.get(key="practising-certificate")  # type: ignore[union-attr]
    assert q.is_knockout


def test_seed_is_idempotent() -> None:
    seed(PASSWORD)
    second = seed(PASSWORD)
    assert second.jobs == []
    assert Organisation.objects.filter(name="MudhoTech Demo Ltd").count() == 1
    assert Job.objects.unscoped().count() == 3
    assert User.objects.filter(email__endswith="-demo.test").count() == 13


@override_settings(DEBUG=False)
def test_command_refuses_without_debug_or_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_PASSWORD", PASSWORD)
    with pytest.raises(CommandError, match="development"):
        call_command("seed_demo")
    monkeypatch.delenv("DEMO_PASSWORD")
    with pytest.raises(CommandError, match="DEMO_PASSWORD"):
        call_command("seed_demo", "--allow-non-debug")
