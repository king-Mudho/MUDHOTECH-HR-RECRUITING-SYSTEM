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
]
