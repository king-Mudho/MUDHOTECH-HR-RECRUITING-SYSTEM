"""In-app notification inbox (P05-T05)."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.notifications import delivery
from apps.notifications.api.inbox import relative_link

pytestmark = pytest.mark.django_db


def tell(user: Any, key: str, dedupe: str, **context: Any) -> None:
    base = {"organisation_name": "Acme", "job_title": "Developer"}
    with transaction.atomic():
        delivery.notify(user, key, {**base, **context}, dedupe_key=dedupe)


def client(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)
    return c


def test_list_count_read_and_read_all() -> None:
    user = UserFactory()
    tell(user, "shortlisted", "a", application_url="http://localhost:3000/candidate/applications/7")
    tell(user, "recruitment_paused", "b")
    tell(UserFactory(), "shortlisted", "c")  # someone else's
    c = client(user)
    assert c.get("/api/v1/notifications/unread-count/").json() == {"count": 2}
    body = c.get("/api/v1/notifications/").json()
    assert body["count"] == 2
    newest, oldest = body["results"]
    assert newest["key"] == "recruitment_paused" and "paused" in newest["text"]
    assert oldest["link"] == "/candidate/applications/7" and oldest["read_at"] is None
    assert "Acme moved your application for Developer" in oldest["text"]
    read = c.post(f"/api/v1/notifications/{oldest['id']}/read/").json()
    assert read["read_at"] is not None
    assert c.get("/api/v1/notifications/unread-count/").json() == {"count": 1}
    assert [r["id"] for r in c.get("/api/v1/notifications/?unread=1").json()["results"]] == [
        newest["id"]
    ]
    assert c.post("/api/v1/notifications/read-all/").json() == {"count": 0}
    assert c.get("/api/v1/notifications/unread-count/").json() == {"count": 0}


def test_other_users_notifications_are_invisible() -> None:
    owner, intruder = UserFactory(), UserFactory()
    tell(owner, "shortlisted", "a")
    item = client(owner).get("/api/v1/notifications/").json()["results"][0]
    c = client(intruder)
    assert c.get("/api/v1/notifications/").json()["count"] == 0
    assert c.post(f"/api/v1/notifications/{item['id']}/read/").status_code == 404
    c.post("/api/v1/notifications/read-all/")
    assert client(owner).get("/api/v1/notifications/unread-count/").json() == {"count": 1}
    assert APIClient().get("/api/v1/notifications/").status_code in (401, 403)


def test_links_are_only_paths_on_our_site() -> None:
    assert relative_link(
        {"application_url": "http://localhost:3000/candidate/applications/1#x"}
    ) == ("/candidate/applications/1#x")
    # only the path is kept, so a foreign host can't send anyone off-site
    assert relative_link({"application_url": "https://evil.example/phish"}) == "/phish"
    assert relative_link(
        {"message_url": "https://old-domain.example/candidate/applications/2#messages"}
    ) == ("/candidate/applications/2#messages")
    assert relative_link({"application_url": "//evil.example/phish"}) == "/phish"
    assert relative_link({"application_url": "javascript:alert(1)"}) == ""
    assert relative_link({}) == ""
