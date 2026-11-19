"""Stored analytics snapshots (P13-T03).

The nightly job and the on-demand refresh store the computed report for an organisation's
default view (last 90 days, all vacancies) so the reports page opens instantly. This is a tenant
table (row-level security applies) rather than a PostgreSQL materialised view, which would bypass
RLS. Filtered views are always computed live from the raw data.
"""

from __future__ import annotations

from django.db import models

from apps.core.models import TenantModel


class AnalyticsSnapshot(TenantModel):
    key = models.CharField(max_length=40, default="default")
    computed_at = models.DateTimeField()
    params = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-computed_at",)
        constraints = [
            models.UniqueConstraint(fields=["organisation", "key"], name="uniq_analytics_snapshot")
        ]
