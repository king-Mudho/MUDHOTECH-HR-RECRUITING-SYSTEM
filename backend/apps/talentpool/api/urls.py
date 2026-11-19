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
]
