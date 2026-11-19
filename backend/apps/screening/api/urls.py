from django.urls import path

from . import governance, views

urlpatterns = [
    path("platform/ai/", governance.PlatformAIView.as_view(), name="platform-ai"),
    path(
        "platform/ai/quality/",
        governance.PlatformAIQualityView.as_view(),
        name="platform-ai-quality",
    ),
    path(
        "platform/ai/organisations/<uuid:organisation_id>/",
        governance.PlatformOrgAIView.as_view(),
        name="platform-ai-org",
    ),
    path(
        "hr/jobs/<uuid:job_id>/screening-runs/",
        views.JobScreeningRunsView.as_view(),
        name="hr-job-screening-runs",
    ),
    path(
        "hr/jobs/<uuid:job_id>/screening-analytics/",
        views.JobScreeningAnalyticsView.as_view(),
        name="hr-job-screening-analytics",
    ),
    path(
        "hr/screening-runs/<uuid:run_id>/",
        views.ScreeningRunView.as_view(),
        name="hr-screening-run",
    ),
    path(
        "hr/applications/<uuid:application_id>/evaluation/",
        views.ApplicationEvaluationView.as_view(),
        name="hr-application-evaluation",
    ),
    path(
        "hr/applications/<uuid:application_id>/evaluations/",
        views.ApplicationEvaluationsView.as_view(),
        name="hr-application-evaluations",
    ),
    path(
        "hr/applications/<uuid:application_id>/evaluations/<int:version>/",
        views.ApplicationEvaluationVersionView.as_view(),
        name="hr-application-evaluation-version",
    ),
    path(
        "hr/applications/<uuid:application_id>/verifications/",
        views.ApplicationVerificationsView.as_view(),
        name="hr-application-verifications",
    ),
    path(
        "hr/claims/<uuid:claim_id>/verify/",
        views.ClaimVerifyView.as_view(),
        name="hr-claim-verify",
    ),
]
