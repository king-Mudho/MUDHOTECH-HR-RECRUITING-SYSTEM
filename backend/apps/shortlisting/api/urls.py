from django.urls import path

from . import views

urlpatterns = [
    path(
        "hr/jobs/<uuid:job_id>/shortlists/",
        views.JobShortlistsView.as_view(),
        name="hr-job-shortlists",
    ),
    path("hr/shortlists/<uuid:shortlist_id>/", views.ShortlistView.as_view(), name="hr-shortlist"),
    path(
        "hr/shortlists/<uuid:shortlist_id>/entries/",
        views.ShortlistEntriesView.as_view(),
        name="hr-shortlist-entries",
    ),
    path(
        "hr/shortlists/<uuid:shortlist_id>/refresh/",
        views.ShortlistRefreshView.as_view(),
        name="hr-shortlist-refresh",
    ),
    path(
        "hr/shortlists/<uuid:shortlist_id>/submit/",
        views.ShortlistSubmitView.as_view(),
        name="hr-shortlist-submit",
    ),
    path(
        "hr/shortlists/<uuid:shortlist_id>/approve/",
        views.ShortlistApproveView.as_view(),
        name="hr-shortlist-approve",
    ),
    path(
        "hr/shortlists/<uuid:shortlist_id>/reject/",
        views.ShortlistRejectView.as_view(),
        name="hr-shortlist-reject",
    ),
    path(
        "hr/shortlists/<uuid:shortlist_id>/undo/",
        views.ShortlistUndoView.as_view(),
        name="hr-shortlist-undo",
    ),
]
