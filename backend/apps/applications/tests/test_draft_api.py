"""Draft APIs (P04-T07): resume, autosave + lock, documents, answers with branching, review."""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.applications import answers as ans
from apps.applications.models import Application, Status
from apps.applications.services import next_reference
from apps.applications.tests.factories import published_job
from apps.core.time import now
from apps.documents.models import Document, ScanStatus
from apps.questionnaires.models import Questionnaire, QuestionResponse
from apps.questionnaires.services import replace_questions

pytestmark = pytest.mark.django_db

QUESTIONS: list[dict[str, Any]] = [
    {"key": "licence", "type": "yes_no", "prompt": "Driver's licence?", "required": True},
    {
        "key": "licence-class",
        "type": "single_choice",
        "prompt": "Which class?",
        "required": True,
        "options": [{"label": "Class 4", "value": "c4"}, {"label": "Class 2", "value": "c2"}],
        "branching": {"show_if": {"question": "licence", "op": "eq", "value": "yes"}},
    },
    {
        "key": "years",
        "type": "number",
        "prompt": "Years?",
        "required": True,
        "config": {"min": 0, "max": 50},
    },
    {
        "key": "why",
        "type": "long_text",
        "prompt": "Why?",
        "required": False,
        "config": {"word_limit": 5},
    },
]


@pytest.fixture
def job() -> Any:
    job = published_job()
    qn = Questionnaire.objects.create(
        organisation=job.organisation, job_version=job.published_version
    )
    replace_questions(qn, QUESTIONS, actor=None)
    return job


@pytest.fixture
def candidate() -> Any:
    user = UserFactory()
    user.email_verified_at = now()
    user.save(update_fields=["email_verified_at"])
    return user


@pytest.fixture
def client(candidate: Any) -> APIClient:
    c = APIClient()
    c.force_login(candidate)
    return c


def start(client: APIClient, job: Any) -> dict[str, Any]:
    res = client.post("/api/v1/applications/", {"job_id": str(job.pk)}, format="json")
    assert res.status_code in (200, 201), res.content
    return res.json()


def doc(user: Any, **kw: Any) -> Document:
    fields: dict[str, Any] = {
        "owner_user": user,
        "purpose": "cv",
        "original_filename": "cv.pdf",
        "size_bytes": 1000,
        "storage_key": "cv/x.pdf",
        "scan_status": ScanStatus.CLEAN,
        **kw,
    }
    return Document.objects.create(**fields)


def test_start_resume_list_and_isolation(client: APIClient, job: Any) -> None:
    first = client.post("/api/v1/applications/", {"job_id": str(job.pk)}, format="json")
    assert first.status_code == 201
    body = first.json()
    assert (
        body["status"] == "draft"
        and body["job"]["title"] == job.title
        and body["reference"] is None
    )
    again = client.post("/api/v1/applications/", {"job_id": str(job.pk)}, format="json")
    assert again.status_code == 200 and again.json()["id"] == body["id"]
    assert [a["id"] for a in client.get("/api/v1/applications/").json()] == [body["id"]]
    other = APIClient()
    other.force_login(UserFactory())
    assert other.get(f"/api/v1/applications/{body['id']}/").status_code == 404
    assert other.get(f"/api/v1/applications/{body['id']}/review/").status_code == 404
    assert (
        other.put(
            f"/api/v1/applications/{body['id']}/answers/", {"answers": []}, format="json"
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/applications/",
            {"job_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        ).status_code
        == 404
    )


def test_autosave_contact_with_lock(client: APIClient, job: Any) -> None:
    app = start(client, job)
    url = f"/api/v1/applications/{app['id']}/"
    res = client.patch(
        url,
        {
            "lock_version": app["lock_version"],
            "contact": {"first_name": "Tendai", "phone": "0772123456"},
            "last_step": 2,
        },
        format="json",
    )
    assert res.status_code == 200, res.content
    assert res.json()["contact"] == {"first_name": "Tendai", "phone": "+263772123456"}
    assert res.json()["last_step"] == 2
    stale = client.patch(url, {"lock_version": app["lock_version"], "last_step": 3}, format="json")
    assert stale.status_code == 409


def test_answers_validation_and_branching_discard(client: APIClient, job: Any) -> None:
    app = start(client, job)
    url = f"/api/v1/applications/{app['id']}/answers/"
    bad = client.put(
        url,
        {"answers": [{"key": "years", "value": 99}, {"key": "nope", "value": 1}]},
        format="json",
    )
    assert bad.status_code == 400
    assert set(bad.json()["error"]["details"]) == {"years", "nope"}
    too_long = client.put(
        url, {"answers": [{"key": "why", "value": "one two three four five six"}]}, format="json"
    )
    assert too_long.status_code == 400
    ok = client.put(
        url,
        {
            "answers": [
                {"key": "licence", "value": "yes"},
                {"key": "licence-class", "value": "c4"},
                {"key": "years", "value": 3},
            ]
        },
        format="json",
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["answers"] == {"licence": "yes", "licence-class": "c4", "years": 3}
    assert "licence-class" in ok.json()["visible_questions"]
    # Changing the parent hides the follow-up and discards its stored answer.
    hidden = client.put(url, {"answers": [{"key": "licence", "value": "no"}]}, format="json").json()
    assert "licence-class" not in hidden["visible_questions"]
    assert hidden["answers"] == {"licence": "no", "years": 3}
    app_obj = Application.objects.unscoped().get(pk=app["id"])
    assert (
        not QuestionResponse.objects.unscoped()
        .filter(application=app_obj, question__key="licence-class")
        .exists()
    )
    # Hidden answers sent anyway are ignored.
    ignored = client.put(
        url, {"answers": [{"key": "licence-class", "value": "c2"}]}, format="json"
    ).json()
    assert "licence-class" not in ignored["answers"]


def test_documents_rules(client: APIClient, job: Any, candidate: Any) -> None:
    app = start(client, job)
    url = f"/api/v1/applications/{app['id']}/documents/"
    pending = doc(candidate, scan_status=ScanStatus.PENDING)
    ok = client.put(
        url,
        {"documents": [{"document_id": str(pending.pk), "role": "cv", "required_doc_key": "cv"}]},
        format="json",
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["documents"][0]["scan_status"] == "pending"
    someone_elses = doc(UserFactory())
    infected = doc(candidate, scan_status=ScanStatus.INFECTED)
    for bad_id in (someone_elses.pk, infected.pk):
        res = client.put(
            url, {"documents": [{"document_id": str(bad_id), "role": "cv"}]}, format="json"
        )
        assert res.status_code == 400
    big = [doc(candidate, size_bytes=10 * 1024 * 1024) for _ in range(3)]
    res = client.put(
        url,
        {"documents": [{"document_id": str(d.pk), "role": "other"} for d in big]},
        format="json",
    )
    assert res.status_code == 413


def test_review_lists_everything_missing_then_ready(
    client: APIClient, job: Any, candidate: Any
) -> None:
    app = start(client, job)
    review = client.get(f"/api/v1/applications/{app['id']}/review/").json()
    codes = {(m["code"], m["key"]) for m in review["missing"]}
    assert ("document_required", "cv") in codes
    assert {("answer_required", "licence"), ("answer_required", "years")} <= codes
    assert ("answer_required", "licence-class") not in codes  # hidden until licence=yes
    assert not review["ready"]
    client.put(
        f"/api/v1/applications/{app['id']}/documents/",
        {"documents": [{"document_id": str(doc(candidate).pk), "role": "cv"}]},
        format="json",
    )
    client.put(
        f"/api/v1/applications/{app['id']}/answers/",
        {"answers": [{"key": "licence", "value": "no"}, {"key": "years", "value": 2}]},
        format="json",
    )
    ready = client.get(f"/api/v1/applications/{app['id']}/review/").json()
    assert ready["ready"] is True and ready["missing"] == []


def test_unverified_email_is_listed(job: Any) -> None:
    """EC-ACC-03: drafting is allowed; the review flags the unverified email."""
    user = UserFactory(verified=False)
    c = APIClient()
    c.force_login(user)
    app = start(c, job)
    codes = [
        m["code"] for m in c.get(f"/api/v1/applications/{app['id']}/review/").json()["missing"]
    ]
    assert "email_unverified" in codes


def test_submitted_applications_cannot_be_edited(client: APIClient, job: Any) -> None:
    app = start(client, job)
    Application.objects.unscoped().filter(pk=app["id"]).update(
        status=Status.SUBMITTED, reference=next_reference(job.organisation)
    )
    res = client.put(
        f"/api/v1/applications/{app['id']}/answers/",
        {"answers": [{"key": "years", "value": 1}]},
        format="json",
    )
    assert res.status_code == 409 and res.json()["error"]["code"] == "conflict.not_draft"


@pytest.mark.parametrize(
    ("q", "value", "ok"),
    [
        ({"type": "yes_no"}, "YES", True),
        ({"type": "yes_no"}, "maybe", False),
        ({"type": "multiple_choice", "options": ["a", "b"]}, ["a", "a", "b"], True),
        ({"type": "multiple_choice", "options": ["a"]}, ["z"], False),
        ({"type": "scale"}, 6, False),
        ({"type": "scale"}, 2.5, False),
        ({"type": "date"}, "2026-13-01", False),
        ({"type": "date"}, "2026-12-01", True),
        ({"type": "short_text"}, "x" * 301, False),
        ({"type": "salary_expectation", "config": {"min": 0}}, "1200.50", True),
    ],
)
def test_validate_answer_types(q: dict[str, Any], value: Any, ok: bool) -> None:
    _, err = ans.validate_answer({"key": "k", **q}, value)
    assert (err is None) == ok, err


def test_visibility_ops() -> None:
    qs = [
        {"key": "n", "type": "number"},
        {
            "key": "senior",
            "type": "yes_no",
            "branching": {"show_if": {"question": "n", "op": "gte", "value": 5}},
        },
        {
            "key": "lead",
            "type": "yes_no",
            "branching": {"show_if": {"question": "senior", "op": "eq", "value": "yes"}},
        },
        {
            "key": "any",
            "type": "short_text",
            "branching": {"show_if": {"question": "n", "op": "answered"}},
        },
    ]
    assert ans.visible_keys(qs, {}) == ["n"]
    assert ans.visible_keys(qs, {"n": 7, "senior": "yes"}) == ["n", "senior", "lead", "any"]
    # A hidden parent hides its children even if they were answered earlier.
    assert ans.visible_keys(qs, {"n": 2, "senior": "yes"}) == ["n", "any"]
