from django.urls import path

from . import views

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
]
