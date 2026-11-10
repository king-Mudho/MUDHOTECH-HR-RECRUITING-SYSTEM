"""HR vacancy endpoints for the cross-tenant suite and the permission matrix (P03-T11)."""

from __future__ import annotations

import functools
from datetime import timedelta
from typing import Any

from tests.tenancy.registry import Ctx, Endpoint

STAGES = ("job", "review_job", "approved_job", "live_job", "paused_job", "flagged_job")

CRITERIA = [
    {
        "type": "skill",
        "importance": "essential",
        "title": "Python",
        "justification": "Our platform is written in Python.",
    },
    {"type": "experience", "importance": "preferred", "title": "Web development"},
]
QUESTIONS = [
    {
        "key": "portfolio",
        "type": "yes_no",
        "prompt": "Can you share a code sample?",
        "scoring": {"mode": "exact", "expected": "yes"},
    }
]


def jobs_setup(ctx: Ctx, needs: tuple[str, ...] = STAGES) -> None:
    from apps.core import flags
    from apps.core.time import now
    from apps.jobs import services
    from apps.jobs.models import JobAssignment
    from apps.organisations.models import Membership, OrganisationPolicy

    team, org = ctx.team, ctx.team.org
    org.verified_at = now()
    org.save(update_fields=["verified_at"])
    OrganisationPolicy.objects.filter(organisation=org).update(
        privacy_notice="We use your data to assess your application."
    )
    flags.set_flag("jobs.ai_suggestions", True, org)
    flags.invalidate("jobs.ai_suggestions")
    hiring = Membership.objects.for_org(org).get(user=team.hiring_manager)

    def build(stage: str, questions: list[dict[str, Any]] | None = None) -> Any:
        job = services.create_job(
            org,
            actor=team.recruiter,
            data={
                "title": f"Software Developer ({stage})",
                "closes_at": now() + timedelta(days=21),
                "location_ids": [ctx.objects["location"].pk],
                "summary": "Build web applications.",
                "responsibilities_html": "<p>Write code</p>",
                "required_documents": ["cv"],
            },
        )
        JobAssignment.objects.create(
            organisation=org, job=job, membership=hiring, role_on_job="hiring_manager"
        )
        services.set_criteria(job, actor=team.recruiter, criteria=CRITERIA)
        services.set_questionnaire(job, actor=team.recruiter, questions=questions or QUESTIONS)
        if stage in {"review", "approved", "live", "paused", "open"}:
            services.submit_for_approval(job, actor=team.recruiter)
        if stage in {"approved", "live", "paused", "open"}:
            services.approve(job, actor=team.hr_manager)
        if stage in {"live", "paused", "open"}:
            services.publish(job, actor=team.hr_manager)
        if stage == "open":  # test data: no required documents, so JSON-only applications work
            from apps.jobs.models import JobVersion

            JobVersion.objects.for_org(org).filter(pk=job.current_version_id).update(
                required_documents=[]
            )
        if stage == "paused":
            services.pause(job, actor=team.hr_manager)
        job.refresh_from_db()
        return job

    flagged = [*QUESTIONS, {"key": "age", "type": "number", "prompt": "What is your age?"}]
    for name in needs:
        stage = name.removesuffix("_job") if name != "job" else "draft"
        ctx.objects[name] = build(stage, flagged if name == "flagged_job" else None)


def _jobs(c: Ctx) -> str:
    return "/api/v1/hr/jobs"


def _job(name: str = "job") -> Any:
    return lambda c: f"/api/v1/hr/jobs/{c.objects[name].pk}"


def _future(days: int) -> str:
    from apps.core.time import now

    return (now() + timedelta(days=days)).isoformat()


@functools.cache
def _setup_for(needs: tuple[str, ...]) -> Any:
    return lambda ctx: jobs_setup(ctx, needs)


def ep(name: str, method: str, path: Any, act: str, **kw: Any) -> Endpoint:
    """Each endpoint builds only the vacancy states it uses (keeps the matrix fast)."""
    kw.setdefault("setup", _setup_for(tuple(kw.pop("needs", ("job",)))))
    return Endpoint(name, method, path, act, org_header=True, **kw)


JOB_ENDPOINTS: list[Endpoint] = [
    ep(
        "hr-jobs",
        "get",
        lambda c: f"{_jobs(c)}/",
        "jobs.view",
        is_list=True,
        targets_object=False,
    ),
    ep(
        "hr-jobs",
        "post",
        lambda c: f"{_jobs(c)}/",
        "jobs.create",
        success=201,
        targets_object=False,
        data=lambda c: {"title": "Accountant"},
    ),
    ep("hr-job", "get", lambda c: f"{_job()(c)}/", "jobs.view"),
    ep(
        "hr-job",
        "patch",
        lambda c: f"{_job()(c)}/",
        "jobs.create",
        data=lambda c: {"lock_version": c.objects["job"].lock_version, "summary": "Updated"},
    ),
    ep(
        "hr-job-criteria",
        "put",
        lambda c: f"{_job()(c)}/criteria/",
        "jobs.create",
        data=lambda c: {"criteria": CRITERIA},
    ),
    ep(
        "hr-job-rubric",
        "put",
        lambda c: f"{_job()(c)}/rubric/",
        "jobs.create",
        data=lambda c: {"categories": _rubric()},
    ),
    ep(
        "hr-job-questionnaire",
        "put",
        lambda c: f"{_job()(c)}/questionnaire/",
        "jobs.create",
        data=lambda c: {"questions": QUESTIONS},
    ),
    ep("hr-job-lint", "post", lambda c: f"{_job()(c)}/lint/", "jobs.view"),
    ep("hr-job-ai-suggestions", "post", lambda c: f"{_job()(c)}/ai-suggestions/", "jobs.create"),
    ep(
        "hr-job-protected-exception",
        "post",
        lambda c: f"{_job('flagged_job')(c)}/questions/age/protected-exception/",
        "questions.protected_exception",
        data=lambda c: {"reason": "Statutory minimum age of 18 applies to this role."},
        needs=("flagged_job",),
    ),
    ep("hr-job-submit", "post", lambda c: f"{_job()(c)}/submit-for-approval/", "jobs.create"),
    ep(
        "hr-job-approve",
        "post",
        lambda c: f"{_job('review_job')(c)}/approve/",
        "jobs.approve",
        needs=("review_job",),
    ),
    ep(
        "hr-job-reject",
        "post",
        lambda c: f"{_job('review_job')(c)}/reject/",
        "jobs.approve",
        data=lambda c: {"reason": "Please add salary details."},
        needs=("review_job",),
    ),
    ep(
        "hr-job-publish",
        "post",
        lambda c: f"{_job('approved_job')(c)}/publish/",
        "jobs.publish",
        needs=("approved_job",),
    ),
    ep(
        "hr-job-schedule",
        "post",
        lambda c: f"{_job('approved_job')(c)}/schedule/",
        "jobs.publish",
        data=lambda c: {"publish_at": _future(2)},
        needs=("approved_job",),
    ),
    ep(
        "hr-job-pause",
        "post",
        lambda c: f"{_job('live_job')(c)}/pause/",
        "jobs.publish",
        needs=("live_job",),
    ),
    ep(
        "hr-job-resume",
        "post",
        lambda c: f"{_job('paused_job')(c)}/resume/",
        "jobs.publish",
        needs=("paused_job",),
    ),
    ep(
        "hr-job-close",
        "post",
        lambda c: f"{_job('live_job')(c)}/close/",
        "jobs.publish",
        data=lambda c: {"reason": "Position filled"},
        needs=("live_job",),
    ),
    ep("hr-job-archive", "post", lambda c: f"{_job()(c)}/archive/", "jobs.publish"),
    ep(
        "hr-job-extend",
        "post",
        lambda c: f"{_job('live_job')(c)}/extend-deadline/",
        "jobs.publish",
        data=lambda c: {"closes_at": _future(40), "reason": "Few applicants so far"},
        needs=("live_job",),
    ),
    ep(
        "hr-job-duplicate",
        "post",
        lambda c: f"{_job('live_job')(c)}/duplicate/",
        "jobs.create",
        success=201,
        needs=("live_job",),
    ),
    ep(
        "hr-job-new-version",
        "post",
        lambda c: f"{_job('live_job')(c)}/new-version/",
        "jobs.approve",
        success=201,
        data=lambda c: {"reason": "Add Django as a requirement"},
        needs=("live_job",),
    ),
    ep("hr-job-assignments", "get", lambda c: f"{_job()(c)}/assignments/", "jobs.view"),
    ep(
        "hr-job-assignments",
        "put",
        lambda c: f"{_job()(c)}/assignments/",
        "jobs.assign",
        data=lambda c: {
            "assignments": [
                {"membership_id": str(_member(c, "recruiter").pk), "role_on_job": "recruiter"}
            ]
        },
    ),
    ep(
        "hr-job-assisted-application",
        "post",
        lambda c: f"{_job('open_job')(c)}/assisted-applications/",
        "applications.transition",
        success=201,
        data=lambda c: {
            "email": f"assisted.{c.org_id[:8]}@example.test",
            "first_name": "Rudo",
            "last_name": "Moyo",
            "consent_confirmed": True,
            "consent_method": "in_person",
            "answers": [{"key": "portfolio", "value": "yes"}],
        },
        needs=("open_job",),
    ),
    ep("hr-job-events", "get", lambda c: f"{_job()(c)}/events/", "jobs.view"),
    ep("hr-job-versions", "get", lambda c: f"{_job()(c)}/versions/", "jobs.view"),
]


def _rubric() -> list[dict[str, Any]]:
    from apps.jobs.services import default_rubric

    return default_rubric()


def _member(c: Ctx, role: str) -> Any:
    from apps.organisations.models import Membership

    return Membership.objects.for_org(c.team.org).get(user=getattr(c.team, role))
