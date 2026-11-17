"""Audit trail queries for auditors and organisation admins (P08-T11)."""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.utils.dateparse import parse_date

from apps.organisations.models import Membership

from .models import AuditEvent


def events_for(membership: Membership, params: dict[str, Any]) -> QuerySet[AuditEvent]:
    qs = AuditEvent.objects.filter(organisation_id=membership.organisation_id).select_related(
        "actor"
    )
    if value := params.get("target_type"):
        qs = qs.filter(target_type=value)
    if value := params.get("target_id"):
        qs = qs.filter(target_id=str(value))
    if value := params.get("actor"):
        qs = qs.filter(actor_id=value)
    if value := params.get("action"):
        qs = qs.filter(action__startswith=str(value)[:100])
    if (start := parse_date(str(params.get("from") or ""))) is not None:
        qs = qs.filter(created_at__date__gte=start)
    if (end := parse_date(str(params.get("to") or ""))) is not None:
        qs = qs.filter(created_at__date__lte=end)
    return qs
