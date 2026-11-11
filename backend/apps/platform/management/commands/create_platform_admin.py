"""Create (or promote) the platform admin from environment variables (idempotent).

    PLATFORM_ADMIN_EMAIL=ops@example.com PLATFORM_ADMIN_PASSWORD=... \
        python manage.py create_platform_admin

The password is read from the environment only (never a CLI argument, so it does not land in shell
history). The account gets a verified email; MFA becomes mandatory after the 7-day grace period.
"""

from __future__ import annotations

import os
from typing import Any

from allauth.account.models import EmailAddress
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import PlatformRole, User, normalize_email_address
from apps.audit import services as audit
from apps.core import time


class Command(BaseCommand):
    help = (
        "Create or promote the platform admin from PLATFORM_ADMIN_EMAIL / PLATFORM_ADMIN_PASSWORD."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        email = normalize_email_address(os.environ.get("PLATFORM_ADMIN_EMAIL", ""))
        password = os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
        if not email:
            raise CommandError("Set PLATFORM_ADMIN_EMAIL.")
        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            created = user is None
            if created:
                if not password:
                    raise CommandError("Set PLATFORM_ADMIN_PASSWORD to create the account.")
                try:
                    validate_password(password)
                except ValidationError as exc:
                    raise CommandError("; ".join(exc.messages)) from exc
                user = User.objects.create_user(email=email, password=password)
            if user is None:  # pragma: no cover - both branches above set it
                raise CommandError("Could not create the user.")
            user.platform_role = PlatformRole.PLATFORM_ADMIN
            user.is_staff = True
            user.email_verified_at = user.email_verified_at or time.now()
            user.save()
            EmailAddress.objects.update_or_create(
                user=user, email=email, defaults={"verified": True, "primary": True}
            )
            user.start_mfa_grace()
            audit.record(
                action="platform.admin_provisioned", target=user, after={"created": created}
            )
        verb = "Created" if created else "Promoted"
        self.stdout.write(self.style.SUCCESS(f"{verb} platform admin {email}"))
