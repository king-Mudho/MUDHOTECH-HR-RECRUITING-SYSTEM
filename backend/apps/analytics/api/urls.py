from django.urls import path

from . import views as v

urlpatterns = [
    path(
        "hr/reports/recruitment/",
        v.RecruitmentReportView.as_view(),
        name="hr-reports-recruitment",
    ),
    path(
        "hr/reports/recruitment/refresh/",
        v.RecruitmentReportRefreshView.as_view(),
        name="hr-reports-recruitment-refresh",
    ),
    path("hr/exports/", v.ExportListView.as_view(), name="hr-exports"),
    path("hr/exports/<uuid:export_id>/", v.ExportDetailView.as_view(), name="hr-export"),
    path(
        "hr/exports/<uuid:export_id>/download/",
        v.ExportDownloadView.as_view(),
        name="hr-export-download",
    ),
]
