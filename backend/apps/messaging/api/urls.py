from django.urls import path

from . import views as v

urlpatterns = [
    path(
        "applications/<uuid:application_id>/clarifications/",
        v.CandidateClarificationsView.as_view(),
        name="application-clarifications",
    ),
    path(
        "applications/<uuid:application_id>/clarifications/<uuid:clarification_id>/answer/",
        v.CandidateClarificationAnswerView.as_view(),
        name="application-clarification-answer",
    ),
    path(
        "applications/<uuid:application_id>/messages/",
        v.CandidateMessagesView.as_view(),
        name="application-messages",
    ),
    path(
        "hr/clarification-templates/",
        v.HRQuestionTemplatesView.as_view(),
        name="hr-clarification-templates",
    ),
    path(
        "hr/applications/<uuid:application_id>/clarifications/",
        v.HRClarificationsView.as_view(),
        name="hr-application-clarifications",
    ),
    path(
        "hr/applications/<uuid:application_id>/clarifications/<uuid:clarification_id>/cancel/",
        v.HRClarificationCancelView.as_view(),
        name="hr-application-clarification-cancel",
    ),
    path(
        "hr/applications/<uuid:application_id>/messages/",
        v.HRMessagesView.as_view(),
        name="hr-application-messages",
    ),
]
