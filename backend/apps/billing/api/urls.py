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
    path(
        "hr/billing/invoices/<uuid:invoice_id>/pay/",
        v.PayInvoiceView.as_view(),
        name="hr-billing-invoice-pay",
    ),
    path(
        "hr/billing/payments/<uuid:payment_id>/",
        v.PaymentDetailView.as_view(),
        name="hr-billing-payment",
    ),
    path("billing/paynow/result/", v.PaynowResultView.as_view(), name="billing-paynow-result"),
    path(
        "platform/billing/invoices/<uuid:invoice_id>/manual-payment/",
        v.PlatformManualPaymentView.as_view(),
        name="platform-billing-manual-payment",
    ),
]
