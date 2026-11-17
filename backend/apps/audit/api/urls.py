from django.urls import path

from . import views

urlpatterns = [
    path("hr/audit-events/", views.HRAuditEventsView.as_view(), name="hr-audit-events"),
    path(
        "hr/audit-events/export/",
        views.HRAuditExportView.as_view(),
        name="hr-audit-events-export",
    ),
    path(
        "hr/applications/<uuid:application_id>/reconstruct/",
        views.HRReconstructView.as_view(),
        name="hr-application-reconstruct",
    ),
    path(
        "hr/applications/<uuid:application_id>/reconstruct.pdf",
        views.HRReconstructPdfView.as_view(),
        name="hr-application-reconstruct-pdf",
    ),
]
