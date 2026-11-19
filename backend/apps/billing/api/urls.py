from django.urls import path

from . import views as v

urlpatterns = [
    path("hr/billing/", v.BillingOverviewView.as_view(), name="hr-billing"),
    path("hr/billing/invoices/", v.InvoiceListView.as_view(), name="hr-billing-invoices"),
    path(
        "hr/billing/invoices/<uuid:invoice_id>/pdf/",
        v.InvoicePdfView.as_view(),
        name="hr-billing-invoice-pdf",
    ),
]
