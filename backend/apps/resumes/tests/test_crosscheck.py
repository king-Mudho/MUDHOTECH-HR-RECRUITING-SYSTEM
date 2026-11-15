"""Cross-application flags (P06-T12): EC-APP-15/16 - low severity, never an automatic action."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from ai_engine.contracts import Block, DocumentText, Page
from apps.accounts.tests.factories import UserFactory
from apps.applications.models import Status
from apps.audit.models import AuditEvent
from apps.core.models import OutboxEvent
from apps.core.time import now
from apps.documents.models import Document, Purpose, ScanStatus
from apps.resumes import crosscheck, services

from .test_extraction_flow import CORPUS, GOOD_CV, attach, submitted_app

pytestmark = pytest.mark.django_db


def text(first_line: str, rest: str = "Harare | +263 77 000 0000\n\nExperience") -> DocumentText:
    body = f"{first_line}\n{rest}"
    return DocumentText(
        document_id="d",
        sha256="0" * 64,
        mime="application/pdf",
        parser_used="t",
        pages=(Page(number=1, text=body, blocks=(Block(text=body),)),),
    )


def with_name(first: str, last: str) -> Any:
    app = submitted_app(user=UserFactory(first_name=first, last_name=last))
    app.candidate_profile_snapshot = {"first_name": first, "last_name": last}
    return app


@pytest.mark.parametrize(
    ("cv_first_line", "first", "last", "mismatch"),
    [
        ("Takudzwa Chari", "Takudzwa", "Chari", False),
        ("TAKUDZWA CHARI", "Takudzwa", "Chari", False),  # not a name-shaped line: no comparison
        ("Takudzwa P. Chari", "Taku", "Chari", False),  # surname matches
        ("Rudo Moyo-Ncube", "Rudo", "Ncube", False),
        ("Thérèse Dube", "Therese", "Dube", False),  # accents folded
        ("Thérèse Dube", "Rudo", "Moyo", True),  # accented names are names too
        ("Rudo Moyo", "Tendai", "Chari", True),
        ("Curriculum Vitae", "Tendai", "Chari", False),  # a title, not a name
        ("Personal Details", "Tendai", "Chari", False),
        ("Profile", "Tendai", "Chari", False),  # one word: no name line
        ("Software Developer | Harare", "Tendai", "Chari", False),
    ],
)
def test_identity_mismatch(cv_first_line: str, first: str, last: str, mismatch: bool) -> None:
    app = with_name(first, last)
    assert crosscheck.identity_mismatch(app, [text(cv_first_line)]) is mismatch


def test_hidden_first_line_and_no_account_name_are_ignored() -> None:
    app = with_name("", "")
    app.candidate_user.first_name = app.candidate_user.last_name = ""
    assert crosscheck.identity_mismatch(app, [text("Rudo Moyo")]) is False
    other = with_name("Tendai", "Chari")
    hidden_first = DocumentText(
        document_id="d",
        sha256="0" * 64,
        mime="application/pdf",
        parser_used="t",
        pages=(
            Page(
                number=1,
                text="Tendai Chari\n\nRudo Moyo",
                blocks=(
                    Block(text="Tendai Chari"),
                    Block(text="Rudo Moyo", hidden=True, char_start=14),
                ),
            ),
        ),
    )
    assert crosscheck.identity_mismatch(other, [hidden_first]) is False


def _doc(user: Any, sha: str, **kw: Any) -> Document:
    return Document.objects.create(
        owner_user=user,
        purpose=Purpose.CV,
        original_filename="cv.pdf",
        size_bytes=1,
        sha256=sha,
        storage_key=f"k/{sha}/{user.pk}",
        bucket="documents",
        scan_status=ScanStatus.CLEAN,
        **kw,
    )


def test_duplicate_document_across_accounts() -> None:
    app = submitted_app()
    sha = hashlib.sha256(b"cv").hexdigest()
    mine = _doc(app.candidate_user, sha)
    assert crosscheck.duplicate_across_accounts(app, [mine]) is False
    _doc(app.candidate_user, sha)  # my own re-upload is fine
    assert crosscheck.duplicate_across_accounts(app, [mine]) is False
    _doc(UserFactory(), sha, deleted_at=now())  # deleted elsewhere: ignored
    assert crosscheck.duplicate_across_accounts(app, [mine]) is False
    _doc(UserFactory(), sha)
    assert crosscheck.duplicate_across_accounts(app, [mine]) is True
    assert crosscheck.duplicate_across_accounts(app, [_doc(app.candidate_user, "")]) is False


def test_flags_reach_application_evidence_and_audit_without_side_effects(act: Any) -> None:
    app = with_name("Rudo", "Moyo")  # the corpus CV belongs to Takudzwa Chari
    app.save(update_fields=["candidate_profile_snapshot"])
    data = (CORPUS / GOOD_CV).read_bytes()
    doc = attach(app, data)
    Document.objects.filter(pk=doc.pk).update(sha256=hashlib.sha256(data).hexdigest())
    _doc(UserFactory(), hashlib.sha256(data).hexdigest())
    act(services.start, app.pk)
    app.refresh_from_db()
    assert app.status == Status.PROCESSING  # nothing automatic happens
    assert set(app.flags) == {"duplicate_document_across_accounts", "identity_mismatch_possible"}
    (ready,) = OutboxEvent.objects.filter(event_type="application.evidence_ready")
    assert {"duplicate_document_across_accounts", "identity_mismatch_possible"} <= set(
        ready.payload["flags"]
    )
    audit = AuditEvent.objects.get(action="resumes.flags_raised")
    assert audit.after == {
        "flags": ["duplicate_document_across_accounts", "identity_mismatch_possible"]
    }
    assert "Moyo" not in str(audit.after) and "Chari" not in str(audit.after)


def test_matching_owner_gets_no_flags(act: Any) -> None:
    app = with_name("Takudzwa", "Chari")
    app.save(update_fields=["candidate_profile_snapshot"])
    attach(app)
    act(services.start, app.pk)
    app.refresh_from_db()
    assert app.flags == [] and not AuditEvent.objects.filter(action="resumes.flags_raised").exists()
