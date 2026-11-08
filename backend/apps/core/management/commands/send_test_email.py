from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "Send a test email through the configured backend (Mailpit in dev)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--to", default="smoke-test@mhrs.local")

    def handle(self, *args: Any, **options: Any) -> None:
        sent = send_mail(
            subject=f"[{settings.APP_NAME}] Test email",
            message="This is a test email from the MUDHOTECH HR RECRUITING SYSTEM.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[options["to"]],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} test email(s) to {options['to']}"))
