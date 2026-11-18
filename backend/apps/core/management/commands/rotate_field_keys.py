"""Re-encrypt stored values with the primary field-encryption key (docs/runbooks/rotate-keys.md)."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core import crypto
from apps.core.keyrotation import rotate_all


class Command(BaseCommand):
    help = "Re-encrypt every EncryptedTextField value that is not on the primary key yet."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="count only, change nothing")
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args: Any, dry_run: bool, batch_size: int, **options: Any) -> None:
        primary = crypto.keyring().primary_id
        self.stdout.write(f"primary key: {primary}{' (dry run)' if dry_run else ''}")
        try:
            reports = rotate_all(dry_run=dry_run, batch_size=batch_size)
        except crypto.DecryptionError as exc:
            raise CommandError(f"{exc} - is the old key still in FIELD_ENCRYPTION_KEYS?") from exc
        stale = 0
        for r in reports:
            stale += r.stale - r.rotated - r.raced
            keys = ", ".join(f"{k}={n}" for k, n in sorted(r.key_ids.items())) or "-"
            self.stdout.write(
                f"{r.label}: scanned {r.scanned}, on other keys {r.stale}, rotated {r.rotated}, "
                f"changed meanwhile {r.raced} [{keys}]"
            )
        left = sum(r.stale for r in reports) if dry_run else stale
        self.stdout.write(
            self.style.SUCCESS(f"done: {left} value(s) still on an old key")
            if not left
            else self.style.WARNING(f"{left} value(s) still on an old key")
        )
