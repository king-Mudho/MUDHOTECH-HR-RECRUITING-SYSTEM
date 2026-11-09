"""Synthetic demo data (docs/09 §3 `seed_demo`). Development and staging only - never production.

Creates a platform admin, two verified organisations (MudhoTech Demo Ltd, Acme Mining Zimbabwe) with
one user per role, and three published vacancies (Software Developer per Blueprint Appendix A,
Accountant, Registered Nurse) with criteria, rubrics and questionnaires. Idempotent: re-running
reuses existing users/organisations and skips vacancies that already exist. Every person and
organisation here is fictional. Phase 04+ extends it with applications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from allauth.account.models import EmailAddress
from django.db import transaction

from apps.accounts.models import PlatformRole, User
from apps.core import time
from apps.jobs import services as jobs
from apps.jobs.models import Job, JobAssignment
from apps.organisations import services as orgs
from apps.organisations.models import (
    Department,
    Location,
    Membership,
    Organisation,
    OrganisationPolicy,
    Role,
)

PRIVACY_NOTICE = (
    "We use the information in your application only to assess your suitability for this vacancy "
    "and to contact you about it. You can ask to see, correct or delete your data at any time."
)


@dataclass
class OrgSpec:
    key: str
    name: str
    industry: str
    city: str
    description: str
    departments: list[str]
    locations: list[tuple[str, str]]


ORGS = [
    OrgSpec(
        "mudhotech",
        "MudhoTech Demo Ltd",
        "Information technology",
        "Harare",
        "A synthetic software company used to demonstrate MUDHOTECH HR RECRUITING SYSTEM.",
        ["Engineering", "Finance"],
        [("Harare HQ", "Harare"), ("Bulawayo office", "Bulawayo")],
    ),
    OrgSpec(
        "acme",
        "Acme Mining Zimbabwe",
        "Mining",
        "Kadoma",
        "A synthetic mining group with a clinic serving staff and the community.",
        ["Health services", "Finance"],
        [("Kadoma mine", "Kadoma"), ("Harare office", "Harare")],
    ),
]


def _q(key: str, type_: str, prompt: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "type": type_, "prompt": prompt, "required": True, **extra}


@dataclass
class JobSpec:
    org: str
    department: str
    location: str
    title: str
    data: dict[str, Any]
    criteria: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    weights: dict[str, int] = field(default_factory=dict)


def _ess(type_: str, title: str, why: str, **extra: Any) -> dict[str, Any]:
    return {"type": type_, "importance": "essential", "title": title, "justification": why, **extra}


def _pref(type_: str, title: str, **extra: Any) -> dict[str, Any]:
    return {"type": type_, "importance": "preferred", "title": title, **extra}


JOBS = [
    JobSpec(
        org="mudhotech",
        department="Engineering",
        location="Harare HQ",
        title="Software Developer",
        data={
            "workplace_type": "hybrid",
            "employment_type": "full_time",
            "seniority": "mid",
            "openings": 2,
            "salary_min": "1200.00",
            "salary_max": "1800.00",
            "salary_currency": "USD",
            "salary_disclosed": True,
            "summary": "Build reliable web applications, APIs and database-backed services.",
            "responsibilities_html": (
                "<ul><li>Build reliable web applications, APIs and database-backed services</li>"
                "<li>Write tested, maintainable Python code and review colleagues' work</li>"
                "<li>Work with product and frontend colleagues on features end to end</li></ul>"
            ),
            "requirements_html": (
                "<p>Python development, SQL, version control and demonstrable related work. "
                "Django, REST APIs, frontend collaboration and cloud deployment are a plus.</p>"
            ),
            "benefits_html": "<ul><li>Medical aid</li><li>Learning budget</li></ul>",
            "required_documents": ["cv"],
        },
        criteria=[
            _ess("skill", "Python", "Our services are written in Python.", min_months=None),
            _ess("skill", "SQL", "Every service is database-backed."),
            _ess("skill", "Git", "All work goes through version-controlled code review."),
            _ess(
                "experience",
                "Demonstrable related software work",
                "The role builds production services from the start.",
                min_months=12,
                equivalents=["Open-source contributions", "Substantial personal projects"],
                rubric_category="experience",
            ),
            _pref("skill", "Django"),
            _pref("skill", "REST API design"),
            _pref("competency", "Frontend collaboration", rubric_category="competency"),
            _pref("skill", "Cloud deployment"),
        ],
        questions=[
            _q(
                "python-project",
                "long_text",
                "Describe a Python project you worked on and your part in it.",
                config={"word_limit": 300},
                scoring={"mode": "rubric_text", "keywords": ["python", "django", "test", "api"]},
            ),
            _q(
                "api-design",
                "long_text",
                "Give an example of an API you designed. What were the main endpoints?",
                config={"word_limit": 300},
                scoring={"mode": "human"},
            ),
            _q(
                "databases",
                "multiple_choice",
                "Which databases have you used in real projects?",
                options=[
                    {"label": "PostgreSQL", "value": "postgresql", "points": "40"},
                    {"label": "MySQL / MariaDB", "value": "mysql", "points": "30"},
                    {"label": "SQL Server", "value": "sqlserver", "points": "30"},
                    {"label": "MongoDB", "value": "mongodb", "points": "10"},
                ],
                scoring={"mode": "options"},
            ),
            _q("notice", "availability", "What is your notice period (in weeks)?"),
        ],
    ),
    JobSpec(
        org="mudhotech",
        department="Finance",
        location="Harare HQ",
        title="Accountant",
        data={
            "workplace_type": "on_site",
            "employment_type": "full_time",
            "seniority": "mid",
            "salary_currency": "ZWG",
            "summary": "Keep our books accurate, timely and audit-ready.",
            "responsibilities_html": (
                "<ul><li>Prepare monthly management accounts</li>"
                "<li>Reconcile bank and ledger accounts</li>"
                "<li>Prepare ZIMRA tax returns and support the annual audit</li></ul>"
            ),
            "requirements_html": (
                "<p>A recognised accounting qualification and practical experience.</p>"
            ),
            "required_documents": ["cv", "certificates"],
        },
        criteria=[
            _ess(
                "qualification",
                "Accounting degree or ACCA / CIMA / ICAZ part-qualified",
                "The role signs off management accounts.",
                equivalents=["CIS", "CA(Z) in progress"],
            ),
            _ess(
                "experience",
                "Two years' accounting experience",
                "The role works without close supervision.",
                min_months=24,
            ),
            _pref("skill", "Pastel or Sage accounting software"),
            _pref("skill", "Microsoft Excel"),
            _pref("competency", "Attention to detail", rubric_category="competency"),
        ],
        questions=[
            _q(
                "registered",
                "yes_no",
                "Are you registered with, or a student of, a professional accounting body?",
                scoring={"mode": "exact", "expected": "yes"},
            ),
            _q(
                "body",
                "single_choice",
                "Which body?",
                options=[
                    {"label": "ICAZ", "value": "icaz"},
                    {"label": "ACCA", "value": "acca"},
                    {"label": "CIMA", "value": "cima"},
                    {"label": "Other", "value": "other"},
                ],
                branching={"show_if": {"question": "registered", "op": "eq", "value": "yes"}},
            ),
            _q("salary", "salary_expectation", "What are your salary expectations (per month)?"),
        ],
    ),
    JobSpec(
        org="acme",
        department="Health services",
        location="Kadoma mine",
        title="Registered Nurse",
        data={
            "workplace_type": "on_site",
            "employment_type": "contract",
            "openings": 5,
            "salary_min": "700.00",
            "salary_max": "950.00",
            "salary_currency": "USD",
            "salary_disclosed": True,
            "summary": "Provide primary care at our mine clinic for staff and the community.",
            "responsibilities_html": (
                "<ul><li>Run daily outpatient clinics</li><li>Respond to workplace "
                "incidents and emergencies</li><li>Keep accurate patient records</li></ul>"
            ),
            "requirements_html": (
                "<p>Registered General Nurse with a current practising certificate.</p>"
            ),
            "required_documents": ["cv", "certificates", "professional_registration"],
        },
        criteria=[
            _ess(
                "qualification",
                "Registered General Nurse (RGN) diploma",
                "Required by law to practise as a nurse.",
            ),
            _ess(
                "licence",
                "Current Nurses Council of Zimbabwe practising certificate",
                "Required by law to practise as a nurse.",
            ),
            _pref("certification", "Basic Life Support (BLS)"),
            _pref("experience", "Occupational health experience", min_months=12),
        ],
        questions=[
            _q(
                "practising-certificate",
                "yes_no",
                "Do you hold a current Nurses Council of Zimbabwe practising certificate?",
                is_knockout=True,
                knockout_expected="yes",
            ),
            _q(
                "shifts",
                "yes_no",
                "Are you able to work rotating shifts including weekends?",
                scoring={"mode": "exact", "expected": "yes"},
            ),
            _q("start", "date", "When could you start?", required=False),
        ],
    ),
]

ROLE_LOCAL: dict[Role, str] = {
    Role.ORG_ADMIN: "admin",
    Role.HR_MANAGER: "hr",
    Role.RECRUITER: "recruiter",
    Role.HIRING_MANAGER: "manager",
    Role.PANELIST: "panel",
    Role.AUDITOR: "auditor",
}


def _user(email: str, password: str, first: str, last: str, **extra: Any) -> User:
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create_user(email=email, password=password)
    user.first_name, user.last_name = first, last
    user.email_verified_at = user.email_verified_at or time.now()
    for k, v in extra.items():
        setattr(user, k, v)
    user.save()
    EmailAddress.objects.update_or_create(
        user=user, email=email, defaults={"verified": True, "primary": True}
    )
    return user


@dataclass
class SeedResult:
    users: list[str] = field(default_factory=list)
    organisations: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)


@transaction.atomic
def seed(password: str) -> SeedResult:
    result = SeedResult()
    admin = _user(
        "admin@mhrs-demo.test",
        password,
        "Platform",
        "Admin",
        platform_role=PlatformRole.PLATFORM_ADMIN,
        is_staff=True,
    )
    result.users.append(admin.email)
    teams: dict[str, dict[Role, User]] = {}
    org_objs: dict[str, Organisation] = {}
    for spec in ORGS:
        domain = f"{spec.key}-demo.test"
        team = {
            role: _user(f"{local}@{domain}", password, spec.name.split()[0], local.title())
            for role, local in ROLE_LOCAL.items()
        }
        org = Organisation.objects.filter(name=spec.name).first()
        if org is None:
            org = orgs.create_organisation(
                user=team[Role.ORG_ADMIN],
                data={
                    "name": spec.name,
                    "industry": spec.industry,
                    "city": spec.city,
                    "country": "ZW",
                    "description": spec.description,
                },
            )
        if org.status != Organisation.Status.ACTIVE or org.verified_at is None:
            from apps.platform.services import verify_organisation

            verify_organisation(org, actor=admin, reason="Demo organisation")
            org.refresh_from_db()
        OrganisationPolicy.objects.filter(organisation=org).update(privacy_notice=PRIVACY_NOTICE)
        for role, user in team.items():
            Membership.objects.unscoped().get_or_create(
                organisation=org, user=user, defaults={"role": role}
            )
        for name in spec.departments:
            Department.objects.for_org(org).get_or_create(organisation=org, name=name)
        for name, city in spec.locations:
            Location.objects.for_org(org).get_or_create(
                organisation=org, name=name, defaults={"city": city}
            )
        teams[spec.key], org_objs[spec.key] = team, org
        result.organisations.append(org.name)
        result.users.extend(u.email for u in team.values())

    for js in JOBS:
        org, team = org_objs[js.org], teams[js.org]
        if Job.objects.for_org(org).filter(title=js.title).exists():
            continue
        dep = Department.objects.for_org(org).get(name=js.department)
        loc = Location.objects.for_org(org).get(name=js.location)
        recruiter, hr = team[Role.RECRUITER], team[Role.HR_MANAGER]
        job = jobs.create_job(
            org,
            actor=recruiter,
            data={
                **js.data,
                "title": js.title,
                "closes_at": time.now() + timedelta(days=30),
                "department_id": dep.pk,
                "location_ids": [loc.pk],
            },
        )
        hiring = Membership.objects.for_org(org).get(user=team[Role.HIRING_MANAGER])
        JobAssignment.objects.for_org(org).get_or_create(
            organisation=org, job=job, membership=hiring, role_on_job="hiring_manager"
        )
        jobs.set_criteria(job, actor=recruiter, criteria=js.criteria)
        jobs.set_questionnaire(job, actor=recruiter, questions=js.questions)
        jobs.submit_for_approval(job, actor=recruiter, note="Initial version")
        jobs.approve(job, actor=hr, comment="Approved for the demo")
        jobs.publish(job, actor=hr)
        result.jobs.append(f"{org.name}: {js.title}")
    return result
