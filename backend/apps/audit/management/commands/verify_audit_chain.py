from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.audit.services import iter_chains, verify_chain


class Command(BaseCommand):
    help = "Recompute audit hash chains and report any break (exit code 1 on failure)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--chain", help="Organisation id or 'platform' (default: all chains)")

    def handle(self, *args: Any, **options: Any) -> None:
        chains = [options["chain"]] if options["chain"] else list(iter_chains())
        breaks = [b for chain in chains for b in verify_chain(chain)]
        for b in breaks:
            self.stderr.write(f"BROKEN chain={b.chain} seq={b.seq}: {b.reason}")
        if breaks:
            raise CommandError(f"{len(breaks)} problem(s) found in {len(chains)} chain(s).")
        self.stdout.write(self.style.SUCCESS(f"OK - {len(chains)} chain(s) verified."))
