from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .context import ActiveOrgView
from .me import MeView
from .views import (
    CompanyView,
    DepartmentViewSet,
    InvitationAcceptView,
    InvitationPreviewView,
    InvitationViewSet,
    LocationViewSet,
    MemberViewSet,
    OrganisationViewSet,
    PolicyView,
)

org_router = SimpleRouter()
org_router.register("departments", DepartmentViewSet, basename="org-departments")
org_router.register("locations", LocationViewSet, basename="org-locations")
org_router.register("members", MemberViewSet, basename="org-members")
org_router.register("invitations", InvitationViewSet, basename="org-invitations")

organisation = OrganisationViewSet.as_view({"get": "retrieve", "patch": "partial_update"})

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/active-org/", ActiveOrgView.as_view(), name="me-active-org"),
    path("organisations/", OrganisationViewSet.as_view({"post": "create"}), name="organisations"),
    path("organisations/<uuid:organisation_id>/", organisation, name="organisation-detail"),
    path(
        "organisations/<uuid:organisation_id>/policies/",
        PolicyView.as_view(),
        name="organisation-policies",
    ),
    path("organisations/<uuid:organisation_id>/", include(org_router.urls)),
    path("invitations/<str:token>/", InvitationPreviewView.as_view(), name="invitation-token"),
    path(
        "invitations/<str:token>/accept/", InvitationAcceptView.as_view(), name="invitation-accept"
    ),
    path("companies/<slug:slug>/", CompanyView.as_view(), name="company"),
]
