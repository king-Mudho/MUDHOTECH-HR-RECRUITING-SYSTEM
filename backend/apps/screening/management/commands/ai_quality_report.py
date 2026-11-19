"""Print the platform AI drift indicators (P13-T07) and store them as the weekly report row."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from apps.screening import monitoring


class Command(BaseCommand):
    help = "Compute AI drift indicators (parse failure trend, score shifts by engine version)."

    def handle(self, *args: Any, **options: Any) -> None:
        report = monitoring.store_platform_report()
        self.stdout.write(json.dumps(report.metrics["drift"], indent=2, default=str))
