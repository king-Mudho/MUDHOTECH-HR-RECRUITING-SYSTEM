"""Organisation billing API (P14-T04/T08). Organisation admins only."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organisations.permissions import HasOrgAction

from .. import entitlements, metering
from ..models import Metric, Plan
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
