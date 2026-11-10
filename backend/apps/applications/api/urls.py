from django.urls import path

from .views import (
    ApplicationAnswersView,
    ApplicationDetailView,
    ApplicationDocumentsView,
    ApplicationListView,
    ApplicationReviewView,
    ApplicationSubmitView,
)

urlpatterns = [
    path("applications/", ApplicationListView.as_view(), name="applications"),
    path(
        "applications/<uuid:application_id>/", ApplicationDetailView.as_view(), name="application"
    ),
    path(
        "applications/<uuid:application_id>/documents/",
        ApplicationDocumentsView.as_view(),
        name="application-documents",
    ),
    path(
        "applications/<uuid:application_id>/answers/",
        ApplicationAnswersView.as_view(),
        name="application-answers",
    ),
    path(
        "applications/<uuid:application_id>/review/",
        ApplicationReviewView.as_view(),
        name="application-review",
    ),
    path(
        "applications/<uuid:application_id>/submit/",
        ApplicationSubmitView.as_view(),
        name="application-submit",
    ),
]
