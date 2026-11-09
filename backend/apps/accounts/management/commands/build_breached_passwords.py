"""Build the hashed breached-password list used by ``BreachedPasswordValidator``.

python manage.py build_breached_passwords                      # from Django's common list
python manage.py build_breached_passwords --source top100k.txt --output /path/list.sha1.gz
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import django.contrib.auth.password_validation as django_pv
from django.core.management.base import BaseCommand, CommandParser

from apps.accounts.password_validation import DEFAULT_FILE, sha1_hex


class Command(BaseCommand):
    help = "Build a gzipped SHA-1 list of breached/common passwords."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--source", help="Plain-text list (one password per line, .gz ok).")
        parser.add_argument("--output", default=str(DEFAULT_FILE))

    def handle(self, *args: Any, **options: Any) -> None:
        source = Path(
            options["source"]
            or Path(django_pv.__file__).resolve().parent / "common-passwords.txt.gz"
        )
        opener: Any = gzip.open if source.suffix == ".gz" else open
        with opener(source, "rt", encoding="utf-8", errors="ignore") as fh:
            hashes = sorted({sha1_hex(line.strip()) for line in fh if line.strip()})
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the output byte-for-byte reproducible.
        with gzip.GzipFile(output, "wb", mtime=0) as out:
            out.write(("\n".join(hashes) + "\n").encode("ascii"))
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(hashes)} hashes to {output}"))
