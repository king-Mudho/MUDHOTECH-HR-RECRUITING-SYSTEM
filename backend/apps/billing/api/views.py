"""Organisation billing API (P14-T04/T08). Organisation admins only."""

from __future__ import annotations

import contextlib
from typing import Any

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.exceptions import DomainError, NotFoundError
from apps.organisations.permissions import HasOrgAction, IsPlatformAdmin

from .. import entitlements, invoicing, metering, payments
from ..models import Invoice, InvoiceStatus, Metric, Payment, Plan
from . import serializers as s


def _plan(plan: Plan) -> dict[str, Any]:
    return {
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "limits": plan.limits or {},
        "price_usd": plan.price_usd,
        "price_zwg": plan.price_zwg,
        "interval": plan.interval,
        "is_trial": plan.is_trial,
    }


def overview(organisation_id: Any) -> dict[str, Any]:
    sub = entitlements.subscription_for(organisation_id)
    limited = [
        Metric.ACTIVE_VACANCIES,
        Metric.SEATS,
        Metric.AI_EVALUATIONS_MONTH,
        Metric.STORAGE_GB,
    ]
    return {
        "plan": _plan(sub.plan),
        "subscription": {
            "status": sub.status,
            "currency": sub.currency,
            "trial_ends_at": sub.trial_ends_at,
            "current_period_end": sub.current_period_end,
            "grace_until": sub.grace_until,
        },
        "usage": [
            {
                "metric": m.value,
                "label": m.label,
                "used": entitlements.usage(organisation_id, m.value),
                "limit": entitlements.limit_for(sub, m.value) if m in limited else None,
            }
            for m in Metric
        ],
        "history": metering.history(organisation_id),
        "plans": [
            _plan(p) for p in Plan.objects.filter(active=True, is_public=True).order_by("order")
        ],
    }


class BillingOverviewView(APIView):
    permission_classes = [HasOrgAction("billing.view")]

    @extend_schema(operation_id="hr_billing", responses=s.BillingOverviewSerializer)
    def get(self, request: Request) -> Response:
        org_id = request.membership.organisation_id  # type: ignore[attr-defined]
        return Response(s.BillingOverviewSerializer(overview(org_id)).data)


class InvoiceListView(APIView):
    permission_classes = [HasOrgAction("billing.view")]

    @extend_schema(operation_id="hr_billing_invoices", responses=s.InvoiceSerializer(many=True))
    def get(self, request: Request) -> Response:
        org_id = request.membership.organisation_id  # type: ignore[attr-defined]
        rows = Invoice.objects.for_org(org_id).exclude(status=InvoiceStatus.DRAFT)[:50]
        return Response(s.InvoiceSerializer(rows, many=True).data)


class InvoicePdfView(APIView):
    permission_classes = [HasOrgAction("billing.view")]

    @extend_schema(
        operation_id="hr_billing_invoice_pdf",
        responses={(200, "application/pdf"): OpenApiResponse(description="Invoice PDF")},
    )
    def get(self, request: Request, invoice_id: str) -> HttpResponse:
        org_id = request.membership.organisation_id  # type: ignore[attr-defined]
        invoice = (
            Invoice.objects.for_org(org_id)
            .select_related("organisation")
            .exclude(status=InvoiceStatus.DRAFT)
            .filter(pk=invoice_id)
            .first()
        )
        if invoice is None:
            raise NotFoundError()
        response = HttpResponse(invoicing.pdf_bytes(invoice), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.number}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


class PayInvoiceView(APIView):
    permission_classes = [HasOrgAction("billing.manage")]

    @extend_schema(
        operation_id="hr_billing_invoice_pay",
        request=s.PayRequestSerializer,
        responses={201: s.PayResultSerializer},
    )
    def post(self, request: Request, invoice_id: str) -> Response:
        data = s.PayRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment, extra = payments.start_payment(
            request.membership,  # type: ignore[attr-defined]
            invoice_id,
            method=data.validated_data["method"],
            phone=data.validated_data["phone"],
        )
        return Response(s.PayResultSerializer({"payment": payment, **extra}).data, status=201)


class PaymentDetailView(APIView):
    permission_classes = [HasOrgAction("billing.view")]

    @extend_schema(operation_id="hr_billing_payment", responses=s.PaymentSerializer)
    def get(self, request: Request, payment_id: str) -> Response:
        org_id = request.membership.organisation_id  # type: ignore[attr-defined]
        payment = Payment.objects.for_org(org_id).filter(pk=payment_id).first()
        if payment is None:
            raise NotFoundError()
        return Response(s.PaymentSerializer(payment).data)


@method_decorator(csrf_exempt, name="dispatch")
class PaynowResultView(APIView):
    """Paynow's result URL (server to server). Always answers 200 so Paynow stops retrying; the
    message only changes anything after hash verification and a confirming poll (EC-BIL-01)."""

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    @extend_schema(operation_id="billing_paynow_result", request=None, responses={200: None})
    def post(self, request: Request) -> Response:
        from urllib.parse import parse_qsl

        body = request.body.decode("utf-8", errors="replace")[:4000]
        # unverifiable or provider unreachable: nothing changes and the poller keeps checking
        with contextlib.suppress(DomainError):
            payments.handle_result(parse_qsl(body, keep_blank_values=True))
        return Response(status=200)


class PlatformManualPaymentView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_billing_manual_payment",
        request=s.ManualPaymentSerializer,
        responses={201: s.PaymentSerializer},
    )
    def post(self, request: Request, invoice_id: str) -> Response:
        data = s.ManualPaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = payments.record_manual_payment(
            authed_user(request),
            invoice_id,
            amount=data.validated_data["amount"],
            reference=data.validated_data["reference"],
        )
        return Response(s.PaymentSerializer(payment).data, status=201)
