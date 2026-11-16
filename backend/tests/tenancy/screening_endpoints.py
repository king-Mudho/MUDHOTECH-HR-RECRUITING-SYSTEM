"""HR screening endpoints (P07-T10..T12) for the cross-tenant suite and role matrix."""

from __future__ import annotations

from tests.tenancy.registry import Ctx, Endpoint


def screening_setup(ctx: Ctx) -> None:
    """A submitted application with a stored evaluation, an extracted claim and a run."""
    from apps.applications.models import Status
    from apps.documents.models import Document
    from apps.resumes.models import ExtractedClaim, ExtractionRun
    from apps.screening.models import Evaluation, ScreeningRun
    from tests.tenancy.applications_endpoints import applications_setup

    applications_setup(ctx)
    app = ctx.objects["application"]
    type(app).objects.unscoped().filter(pk=app.pk).update(status=Status.UNDER_REVIEW)
    org = app.organisation_id
    Evaluation.objects.create(
        organisation_id=org,
        application=app,
        job_version=app.job_version,
        version=1,
        total_score=70,
        coverage=1,
        band="lower_match",
        input_hash="h",
        engine_version="x",
    )
    ctx.objects["screening_run"] = ScreeningRun.objects.create(
        organisation_id=org,
        job=app.job,
        job_version=app.job_version,
        engine_version="x",
        status="completed",
    )
    document = Document.objects.create(
        owner_user=app.candidate_user,
        purpose="cv",
        original_filename="cv.pdf",
        size_bytes=10,
        storage_key="k",
    )
    run = ExtractionRun.objects.create(
        organisation_id=org, application=app, document=document, engine_version="x"
    )
    ctx.objects["claim"] = ExtractedClaim.objects.create(
        organisation_id=org,
        run=run,
        ordinal=0,
        claim_type="skill",
        method="taxonomy",
        confidence=0.9,
        payload=(
            '{"data":{"type":"skill","raw":"Python"},'
            f'"source":{{"document_id":"{document.pk}","page":1,"snippet":"Python"}},'
            '"method":"taxonomy","confidence":0.9}'
        ),
    )


def _app(c: Ctx) -> str:
    return f"/api/v1/hr/applications/{c.objects['application'].pk}"


def _job(c: Ctx) -> str:
    return f"/api/v1/hr/jobs/{c.objects['live_job'].pk}"


def view(name: str, path: object, **kw: object) -> Endpoint:
    return Endpoint(
        name, "get", path, "applications.view", org_header=True, setup=screening_setup, **kw
    )  # type: ignore[arg-type]


SCREENING_ENDPOINTS: list[Endpoint] = [
    view("hr-job-screening-runs", lambda c: f"{_job(c)}/screening-runs/"),
    view("hr-job-screening-analytics", lambda c: f"{_job(c)}/screening-analytics/"),
    view(
        "hr-screening-run",
        lambda c: f"/api/v1/hr/screening-runs/{c.objects['screening_run'].pk}/",
    ),
    view("hr-application-evaluation", lambda c: f"{_app(c)}/evaluation/"),
    view("hr-application-evaluations", lambda c: f"{_app(c)}/evaluations/"),
    view("hr-application-evaluation-version", lambda c: f"{_app(c)}/evaluations/1/"),
    view("hr-application-verifications", lambda c: f"{_app(c)}/verifications/"),
    Endpoint(
        "hr-job-screening-runs-start",
        "post",
        lambda c: f"{_job(c)}/screening-runs/",
        "applications.transition",
        success=201,
        data=lambda c: {"scope": "pending"},
        org_header=True,
        setup=screening_setup,
    ),
    Endpoint(
        "hr-claim-verify",
        "post",
        lambda c: f"/api/v1/hr/claims/{c.objects['claim'].pk}/verify/",
        "applications.transition",
        success=201,
        data=lambda c: {"decision": "confirmed"},
        org_header=True,
        setup=screening_setup,
    ),
]
