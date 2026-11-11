from django.urls import path

from . import ats as ats_views
from .hr import HRApplicationDetailView, HRJobApplicationsView
from .views import (
    ApplicationAnswersView,
    ApplicationDetailView,
    ApplicationDocumentsView,
    ApplicationListView,
    ApplicationReviewView,
    ApplicationSubmitView,
    ApplicationTimelineView,
    ApplicationWithdrawView,
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
    path(
        "applications/<uuid:application_id>/withdraw/",
        ApplicationWithdrawView.as_view(),
        name="application-withdraw",
    ),
    path(
        "applications/<uuid:application_id>/timeline/",
        ApplicationTimelineView.as_view(),
        name="application-timeline",
    ),
    path(
        "hr/jobs/<uuid:job_id>/applications/",
        HRJobApplicationsView.as_view(),
        name="hr-job-applications",
    ),
    path(
        "hr/applications/<uuid:application_id>/",
        HRApplicationDetailView.as_view(),
        name="hr-application",
    ),
    path(
        "hr/applications/<uuid:application_id>/transition/",
        ats_views.HRTransitionView.as_view(),
        name="hr-application-transition",
    ),
    path(
        "hr/applications/<uuid:application_id>/notes/",
        ats_views.HRNotesView.as_view(),
        name="hr-application-notes",
    ),
    path(
        "hr/applications/<uuid:application_id>/tags/",
        ats_views.HRTagsView.as_view(),
        name="hr-application-tags",
    ),
    path(
        "hr/applications/<uuid:application_id>/assign/",
        ats_views.HRAssignView.as_view(),
        name="hr-application-assign",
    ),
    path(
        "hr/decision-reasons/",
        ats_views.HRDecisionReasonsView.as_view(),
        name="hr-decision-reasons",
    ),
]
