"""Cross-application checks (P06-T12): low-severity flags for HR, never automatic actions.

* ``duplicate_document_across_accounts`` (EC-APP-15): the same file (sha256) was uploaded by a
  different account. Could be a shared template, a family member or fraud - a person decides.
  The flag says only *that* it happened; nothing about the other account or organisation leaks.
* ``identity_mismatch_possible`` (EC-APP-16): the name at the top of the CV shares no name with
  the applicant's account. People use other names, initials, married names - so this is only a
  prompt to look, never a penalty.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from ai_engine.contracts import DocumentText as DocumentTextContract
from ai_engine.extraction.sections import match_heading
from apps.applications.models import Application
from apps.documents.models import Document

from .models import ExtractionRun

DUPLICATE_ACROSS_ACCOUNTS = "duplicate_document_across_accounts"
IDENTITY_MISMATCH = "identity_mismatch_possible"
HEADER_CHARS = 400
NOT_NAMES = frozenset({"curriculum vitae", "resume", "cv", "personal resume", "my cv", "biodata"})
_WORD = re.compile(r"^[^\W\d_][^\W\d_'.-]*(?:['.-][^\W\d_]*)*\.?$")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def account_names(app: Application) -> set[str]:
    snapshot = app.candidate_profile_snapshot or {}
    user = app.candidate_user
    raw = [
        snapshot.get("first_name", ""),
        snapshot.get("last_name", ""),
        snapshot.get("preferred_name", ""),
        getattr(user, "first_name", ""),
        getattr(user, "last_name", ""),
    ]
    return {t for name in raw for t in re.split(r"[\s-]+", fold(str(name or ""))) if len(t) >= 2}


def looks_like_name(line: str) -> bool:
    """2-4 capitalised words of letters (any script), e.g. 'Thérèse N. Dube', not 'PROFILE'."""
    if fold(line).strip(" .:") in NOT_NAMES or match_heading(line) is not None:
        return False
    words = line.split()
    return 2 <= len(words) <= 4 and all(
        _WORD.match(w) and w[0].isupper() and not (len(w) > 2 and w.isupper()) for w in words
    )


def cv_name_line(text: DocumentTextContract) -> str | None:
    """The first visible line of the CV when it looks like a person's name."""
    if not text.pages:
        return None
    for block in text.pages[0].blocks:
        if block.hidden:
            continue
        for line in block.text.split("\n"):
            line = line.strip()
            if not line:
                continue
            return line if looks_like_name(line) else None
    return None


def identity_mismatch(app: Application, texts: Iterable[DocumentTextContract]) -> bool:
    names = account_names(app)
    if not names:
        return False
    for text in texts:
        line = cv_name_line(text)
        if line is None:
            continue  # no clear name at the top (scan, unusual layout): nothing to compare
        header = fold(text.pages[0].text[:HEADER_CHARS])
        tokens = set(re.split(r"[^a-z']+", header))
        if not names & tokens:
            return True
    return False


def duplicate_across_accounts(app: Application, documents: Iterable[Document]) -> bool:
    shas = {d.sha256 for d in documents if d.sha256}
    if not shas:
        return False
    return (
        Document.objects.filter(sha256__in=shas, deleted_at__isnull=True)
        .exclude(owner_user_id=app.candidate_user_id)
        .exists()
    )


def check(app: Application, runs: list[ExtractionRun]) -> list[str]:
    texts: list[DocumentTextContract] = []
    for run in runs:
        stored: Any = getattr(run, "text", None)
        if stored is not None:
            texts.append(DocumentTextContract.model_validate_json(stored.payload))
    flags = []
    if duplicate_across_accounts(app, [r.document for r in runs]):
        flags.append(DUPLICATE_ACROSS_ACCOUNTS)
    if identity_mismatch(app, texts):
        flags.append(IDENTITY_MISMATCH)
    return flags
