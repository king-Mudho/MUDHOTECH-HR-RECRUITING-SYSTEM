from django.urls import path

from . import hr, views

urlpatterns = [
    path(
        "candidate/resumes/<uuid:document_id>/extraction/",
        views.ResumeExtractionView.as_view(),
        name="candidate-resume-extraction",
    ),
    path(
        "candidate/resumes/<uuid:document_id>/import-to-profile/",
        views.ResumeImportView.as_view(),
        name="candidate-resume-import",
    ),
    path(
        "candidate/applications/<uuid:application_id>/extraction/",
        views.ApplicationExtractionView.as_view(),
        name="candidate-application-extraction",
    ),
    path(
        "candidate/claims/<uuid:claim_id>/corrections/",
        views.ClaimCorrectionView.as_view(),
        name="candidate-claim-corrections",
    ),
    path(
        "hr/applications/<uuid:application_id>/extraction/",
        hr.HRExtractionView.as_view(),
        name="hr-application-extraction",
    ),
    path(
        "hr/applications/<uuid:application_id>/evidence-text/",
        hr.HREvidenceTextView.as_view(),
        name="hr-application-evidence-text",
    ),
    path(
        "hr/applications/<uuid:application_id>/retry-processing/",
        hr.HRRetryProcessingView.as_view(),
        name="hr-application-retry-processing",
    ),
]
