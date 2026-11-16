"""Screening fixtures: a vacancy with an approved rubric, criteria and a questionnaire, and an
application whose CV has been read (real extraction of a synthetic corpus CV)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from apps.applications.models import Application
from apps.jobs.models import JobCriterion, Rubric
from apps.organisations.tests.factories import make_org_with_team
from apps.questionnaires.models import Question, Questionnaire
from apps.resumes import engine as resumes_engine
from apps.resumes import services as resumes
from apps.resumes.tests.test_extraction_flow import attach, submitted_app
from apps.taxonomy.models import QualificationLevel, Skill, SkillAlias, SkillRelation

CATEGORIES = [
    {"key": "technical", "label": "Technical skills", "weight": 45},
    {"key": "experience", "label": "Relevant experience", "weight": 30},
    {"key": "qualification", "label": "Qualifications", "weight": 15},
    {"key": "answers", "label": "Screening answers", "weight": 10},
]


@dataclass
class Vacancy:
    team: Any
    job: Any
    criteria: dict[str, JobCriterion]
    knockout: Question
    years: Question


@pytest.fixture(autouse=True)
def _setup(s3: Any, settings: Any) -> None:
    settings.RESUMES_AUTOSTART = True
    settings.SEMANTIC_SKILL_MATCHING = False
    resumes_engine.clear_cache()
    skills = {}
    for name, aliases in [
        ("Python", ["python3"]),
        ("Django", []),
        ("PostgreSQL", ["postgres"]),
        ("SQL", []),
        ("Git", []),
    ]:
        skills[name] = Skill.objects.create(
            canonical_name=name, slug=name.lower(), category="software_it"
        )
        for alias in aliases:
            SkillAlias.objects.create(skill=skills[name], alias=alias)
    SkillRelation.objects.create(
        from_skill=skills["Django"], to_skill=skills["Python"], relation="implies"
    )
    SkillRelation.objects.create(
        from_skill=skills["PostgreSQL"], to_skill=skills["SQL"], relation="implies"
    )
    for code, rank, aliases in [
        ("ZW_ALEVEL", 30, ["ZIMSEC Advanced Level", "A Level"]),
        ("ZW_ND", 50, ["National Diploma"]),
        ("ZW_HND", 60, ["HND", "Higher National Diploma"]),
        ("BACHELOR", 70, ["BSc", "Bachelor"]),
        ("HONOURS", 75, ["Honours", "Hons"]),
    ]:
        level = QualificationLevel.objects.create(code=code, name=code, rank=rank, framework="ZW")
        for alias in aliases:
            level.aliases.create(alias=alias)


@pytest.fixture
def act(django_capture_on_commit_callbacks: Any) -> Any:
    def run(fn: Any, *args: Any, **kwargs: Any) -> Any:
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)

    return run


@pytest.fixture
def vacancy() -> Vacancy:
    from apps.applications.tests.factories import published_job

    team = make_org_with_team()
    job = published_job(organisation=team.org, title="Software Developer")
    version = job.published_version
    Rubric.objects.update_or_create(
        organisation=team.org,
        job_version=version,
        defaults={"categories": CATEGORIES, "total_weight": 100, "status": "approved"},
    )

    def criterion(key: str, **kw: Any) -> JobCriterion:
        return JobCriterion.objects.create(organisation=team.org, job_version=version, **kw)

    criteria = {
        "python": criterion(
            "python",
            type="skill",
            importance="essential",
            title="Python",
            skill=Skill.objects.get(slug="python"),
            rubric_category="technical",
            weight_within_category=2,
            order=1,
        ),
        "sql": criterion(
            "sql",
            type="skill",
            importance="essential",
            title="SQL database experience",
            skill=Skill.objects.get(slug="sql"),
            equivalents=["PostgreSQL"],
            rubric_category="technical",
            order=2,
        ),
        "experience": criterion(
            "experience",
            type="experience",
            importance="essential",
            title="2+ years software development",
            min_months=24,
            rubric_category="experience",
            order=3,
        ),
        "degree": criterion(
            "degree",
            type="qualification",
            importance="preferred",
            title="Degree or HND in computing",
            qualification_level=QualificationLevel.objects.get(code="ZW_HND"),
            rubric_category="qualification",
            order=4,
        ),
    }
    questionnaire = Questionnaire.objects.create(
        organisation=team.org, job_version=version, status="approved"
    )
    knockout = Question.objects.create(
        organisation=team.org,
        questionnaire=questionnaire,
        key="work_permit",
        type="yes_no",
        prompt="Are you allowed to work in Zimbabwe?",
        is_knockout=True,
        config={"knockout_expected": "yes"},
        scoring={"mode": "none"},
        order=1,
    )
    years = Question.objects.create(
        organisation=team.org,
        questionnaire=questionnaire,
        key="years",
        type="number",
        prompt="Years of professional development?",
        scoring={"mode": "range", "min": 2},
        order=2,
    )
    return Vacancy(team=team, job=job, criteria=criteria, knockout=knockout, years=years)


@pytest.fixture
def read_app(vacancy: Vacancy, act: Any) -> Application:
    """An application in ``processing`` whose CV has been read (no screening yet)."""
    app = submitted_app(org=vacancy.team.org)
    Application.objects.unscoped().filter(pk=app.pk).update(
        job=vacancy.job, job_version=vacancy.job.published_version
    )
    app.refresh_from_db()
    attach(app)
    act(resumes.start, app.pk)
    app.refresh_from_db()
    return app
