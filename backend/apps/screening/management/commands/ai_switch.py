"""``manage.py ai_switch off --reason "..." [--org <uuid>]``: AI kill-switch from a shell."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.organisations.models import Organisation
from apps.screening import killswitch


class Command(BaseCommand):
    help = "Switch AI screening on/off for the platform or one organisation (P09-T11)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("state", choices=["on", "off", "inherit", "status"])
        parser.add_argument("--reason", default="")
        parser.add_argument("--org", default=None, help="Organisation id (default: platform-wide)")

    def handle(self, *args: Any, **opts: Any) -> None:
        state, org_id = opts["state"], opts["org"]
        if state != "status":
            if len(opts["reason"].strip()) < 10:
                raise CommandError("--reason is required (at least 10 characters).")
            enabled = {"on": True, "off": False, "inherit": None}[state]
            if org_id:
                org = Organisation.objects.filter(pk=org_id).first()
                if org is None:
                    raise CommandError("Organisation not found.")
                killswitch.set_for_organisation(org, enabled, actor=None, reason=opts["reason"])
            elif enabled is None:
                raise CommandError("'inherit' needs --org.")
            else:
                killswitch.set_platform(enabled, actor=None, reason=opts["reason"])
        self.stdout.write(f"platform: {'on' if killswitch.platform_enabled() else 'OFF'}")
        for oid in killswitch.disabled_organisations():
            self.stdout.write(f"organisation {oid}: OFF (platform override)")
        if org_id:
            allowed = killswitch.ai_allowed(org_id)
            self.stdout.write(f"organisation {org_id}: AI {'allowed' if allowed else 'OFF'}")
