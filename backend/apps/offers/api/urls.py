from django.urls import path

from . import views as v

urlpatterns = [
    path("hr/offers/", v.OfferListView.as_view(), name="hr-offers"),
    path(
        "hr/applications/<uuid:application_id>/offers/",
        v.ApplicationOffersView.as_view(),
        name="hr-application-offers",
    ),
    path("hr/offers/<uuid:offer_id>/", v.OfferView.as_view(), name="hr-offer"),
    path("hr/offers/<uuid:offer_id>/submit/", v.OfferSubmitView.as_view(), name="hr-offer-submit"),
    path(
        "hr/offers/<uuid:offer_id>/approve/", v.OfferApproveView.as_view(), name="hr-offer-approve"
    ),
    path("hr/offers/<uuid:offer_id>/return/", v.OfferReturnView.as_view(), name="hr-offer-return"),
    path("hr/offers/<uuid:offer_id>/issue/", v.OfferIssueView.as_view(), name="hr-offer-issue"),
    path(
        "hr/offers/<uuid:offer_id>/withdraw/",
        v.OfferWithdrawView.as_view(),
        name="hr-offer-withdraw",
    ),
    path("hr/offers/<uuid:offer_id>/letter/", v.OfferLetterView.as_view(), name="hr-offer-letter"),
    path("hr/offers/<uuid:offer_id>/hire/", v.OfferHireView.as_view(), name="hr-offer-hire"),
    path("hr/jobs/<uuid:job_id>/closeout/", v.JobCloseoutView.as_view(), name="hr-job-closeout"),
    # candidate
    path(
        "applications/<uuid:application_id>/offers/",
        v.CandidateApplicationOfferView.as_view(),
        name="candidate-application-offers",
    ),
    path(
        "offers/<uuid:offer_id>/accept/",
        v.CandidateAcceptView.as_view(),
        name="candidate-offer-accept",
    ),
    path(
        "offers/<uuid:offer_id>/decline/",
        v.CandidateDeclineView.as_view(),
        name="candidate-offer-decline",
    ),
]
