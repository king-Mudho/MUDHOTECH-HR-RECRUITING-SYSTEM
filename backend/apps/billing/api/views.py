"""Organisation billing API (P14-T04/T08). Organisation admins only."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundError
from apps.organisations.permissions import HasOrgAction

from .. import entitlements, invoicing, metering
from ..models import Invoice, InvoiceStatus, Metric, Plan
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
