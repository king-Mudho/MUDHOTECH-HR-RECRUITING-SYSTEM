from django.urls import path

from . import views

urlpatterns = [
    path("privacy/requests/", views.MyRightsRequestsView.as_view(), name="privacy-requests"),
    path(
        "privacy/requests/confirm/",
        views.ConfirmRightsRequestView.as_view(),
        name="privacy-requests-confirm",
    ),
    path(
        "privacy/requests/<uuid:request_id>/statement/",
        views.RightsStatementView.as_view(),
        name="privacy-request-statement",
    ),
    path(
        "privacy/requests/<uuid:request_id>/export/",
        views.RightsExportView.as_view(),
        name="privacy-request-export",
    ),
    path("privacy/employers/", views.MyEmployersView.as_view(), name="privacy-employers"),
    path("privacy/consents/", views.MyConsentsView.as_view(), name="privacy-consents"),
    path(
        "privacy/consents/<uuid:consent_id>/withdraw/",
        views.WithdrawConsentView.as_view(),
        name="privacy-consent-withdraw",
    ),
    path("hr/privacy/requests/", views.HRRightsRequestsView.as_view(), name="hr-privacy-requests"),
    path(
        "hr/privacy/requests/<uuid:request_id>/action/",
        views.HRRightsRequestActionView.as_view(),
        name="hr-privacy-request-action",
    ),
    path("hr/legal-holds/", views.HRLegalHoldsView.as_view(), name="hr-legal-holds"),
    path(
        "hr/legal-holds/<uuid:hold_id>/release/",
        views.HRLegalHoldReleaseView.as_view(),
        name="hr-legal-hold-release",
    ),
    path(
        "platform/privacy/requests/",
        views.PlatformRightsRequestsView.as_view(),
        name="platform-privacy-requests",
    ),
    path(
        "platform/privacy/requests/<uuid:request_id>/action/",
        views.PlatformRightsRequestActionView.as_view(),
        name="platform-privacy-request-action",
    ),
]
