from django.urls import path

from .views import (
    DirectUploadView,
    DocumentDownloadView,
    DocumentView,
    UploadCompleteView,
    UploadSessionView,
)

urlpatterns = [
    path(
        "documents/upload-sessions/", UploadSessionView.as_view(), name="documents-upload-sessions"
    ),
    path(
        "documents/upload-sessions/<uuid:session_id>/complete/",
        UploadCompleteView.as_view(),
        name="documents-upload-complete",
    ),
    path("documents/direct-upload/", DirectUploadView.as_view(), name="documents-direct-upload"),
    path("documents/<uuid:document_id>/", DocumentView.as_view(), name="documents-detail"),
    path(
        "documents/<uuid:document_id>/download/",
        DocumentDownloadView.as_view(),
        name="documents-download",
    ),
]
