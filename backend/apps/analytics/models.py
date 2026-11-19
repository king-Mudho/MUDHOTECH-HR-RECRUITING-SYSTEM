"""Stored analytics snapshots (P13-T03).

The nightly job and the on-demand refresh store the computed report for an organisation's
default view (last 90 days, all vacancies) so the reports page opens instantly. This is a tenant
table (row-level security applies) rather than a PostgreSQL materialised view, which would bypass
RLS. Filtered views are always computed live from the raw data.
"""

from __future__ import annotations

from django.conf import settings
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


class ExportJob(TenantModel):
    """A requested export (P13-T06): built on the reports queue, kept 24 h, downloaded through
    15-minute links. Who asked, what and how many rows are audited (EC-PRV-08)."""

    class Kind(models.TextChoices):
        APPLICANTS = "applicants", "Applicants of a vacancy"
        REPORT = "report", "Recruitment report"

    class Format(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel (XLSX)"
        PDF = "pdf", "PDF"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    format = models.CharField(max_length=8, choices=Format.choices)
    params = models.JSONField(default=dict, blank=True)
    blind = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    storage_key = models.CharField(max_length=300, blank=True, default="")
    filename = models.CharField(max_length=200, blank=True, default="")
    row_count = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=200, blank=True, default="")
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["organisation", "status"], name="export_org_status_idx")]
