from django.urls import path

from . import views as v

urlpatterns = [
    path(
        "candidate/talent-pools/",
        v.CandidateTalentPoolsView.as_view(),
        name="candidate-talent-pools",
    ),
    path(
        "candidate/talent-pools/<uuid:organisation_id>/leave/",
        v.CandidateTalentPoolLeaveView.as_view(),
        name="candidate-talent-pool-leave",
    ),
    path("hr/talent-pool/", v.TalentSearchView.as_view(), name="hr-talent-pool"),
    path(
        "hr/talent-pool/<uuid:entry_id>/",
        v.TalentEntryView.as_view(),
        name="hr-talent-pool-entry",
    ),
    path(
        "hr/talent-pool/<uuid:entry_id>/invite/",
        v.TalentInviteView.as_view(),
        name="hr-talent-pool-invite",
    ),
]
