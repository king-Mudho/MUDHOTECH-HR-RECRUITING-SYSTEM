from django.urls import path

from .sessions import RevokeOtherSessionsView, SessionDetailView, SessionListView

urlpatterns = [
    path("me/sessions/", SessionListView.as_view(), name="me-sessions"),
    path(
        "me/sessions/revoke-others/",
        RevokeOtherSessionsView.as_view(),
        name="me-sessions-revoke-others",
    ),
    path("me/sessions/<int:session_id>/", SessionDetailView.as_view(), name="me-session-detail"),
]
