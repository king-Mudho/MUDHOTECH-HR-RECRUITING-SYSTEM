"""Prove that no consequential status change was made without a person (principle 1).

    python manage.py check_human_decisions

Counts application status events into shortlisted / not selected / offer / hired that have no
human actor or no reason. Exits with status 1 when any exist (usable in CI and operations).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.applications.models import ApplicationStatusEvent
from apps.applications.state_machine import HUMAN_ONLY_TARGETS


class Command(BaseCommand):
    help = "Check that every consequential application decision has a human actor and a reason."

    def handle(self, *args: Any, **options: Any) -> None:
        events = ApplicationStatusEvent.objects.unscoped().filter(
            to_status__in=list(HUMAN_ONLY_TARGETS)
        )
        bad = events.filter(Q(actor__isnull=True) | ~Q(actor_type="human") | Q(reason_text=""))
        total, count = events.count(), bad.count()
        self.stdout.write(
            f"{total} consequential transitions checked; "
            f"{count} consequential transitions without a human actor or reason"
        )
        if count:
            raise CommandError(f"{count} consequential transitions lack a human actor or reason")
        self.stdout.write(self.style.SUCCESS("0 consequential transitions without a human actor"))
