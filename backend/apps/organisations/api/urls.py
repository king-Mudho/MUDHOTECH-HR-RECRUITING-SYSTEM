from django.urls import path

from .context import ActiveOrgView

urlpatterns = [
    path("me/active-org/", ActiveOrgView.as_view(), name="me-active-org"),
]
