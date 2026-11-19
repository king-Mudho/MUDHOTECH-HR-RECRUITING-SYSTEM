from django.urls import path

from . import views as v

urlpatterns = [
    path("hr/billing/", v.BillingOverviewView.as_view(), name="hr-billing"),
]
