"""Load tests (P10-T05, NFR-PERF-01): job board reads, candidate submissions, HR applicants list.

Run against a stack started with ``LOAD_TEST=true`` (relaxed per-IP limits, development settings
only) after ``seed_demo``, ``seed_load_accounts --count N`` and, for the HR list,
``run_pilot_benchmark`` or ``seed_core_scenario``. See loadtests/README.md.

User classes (pick with ``locust ... JobBoardUser`` etc.):

* ``JobBoardUser``       - anonymous visitors: board pages, search, vacancy detail;
* ``CandidateSubmitter`` - one synthetic candidate each: sign in, start, upload a synthetic CV,
  answer the questions and submit once (100 or 1,000 users = 100 or 1,000 submissions);
* ``HRReviewer``         - the demo HR manager filtering and paging the applicants list.
"""

from __future__ import annotations

import itertools
import os
import uuid
from pathlib import Path
from typing import Any

from locust import HttpUser, between, task

PASSWORD = os.environ.get("DEMO_PASSWORD", "")
HR_EMAIL = os.environ.get("LOAD_HR_EMAIL", "hr@mudhotech-demo.test")
JOB_TITLE = os.environ.get("LOAD_JOB_TITLE", "Software Developer")
CV = Path(__file__).resolve().parents[1] / "backend" / "fixtures" / "synthetic_cvs"
_ids = itertools.count(1)
_users = itertools.count(int(os.environ.get("LOAD_USER_OFFSET", "0")) + 1)


def _cv_bytes() -> bytes:
    for path in sorted(CV.glob("cv_*_software_developer_strong.pdf")):
        return path.read_bytes()
    raise RuntimeError("synthetic CV corpus not found")


CV_BYTES = _cv_bytes() if CV.exists() else b""


class _Session(HttpUser):
    abstract = True

    def sign_in(self, email: str) -> bool:
        self.client.get("/api/v1/csrf/", name="csrf")
        res = self.client.post(
            "/api/v1/auth/browser/v1/auth/login",
            json={"email": email, "password": PASSWORD},
            headers=self.csrf(),
            name="login",
        )
        return res.status_code == 200

    def csrf(self) -> dict[str, str]:
        token = self.client.cookies.get("csrftoken", "")
        return {"X-CSRFToken": token, "Referer": self.host or ""}


class JobBoardUser(HttpUser):
    """Anonymous visitors (target 200 RPS reads across many users)."""

    wait_time = between(0.5, 1.5)
    weight = 5
    job_ids: list[str] = []

    def on_start(self) -> None:
        if not JobBoardUser.job_ids:
            body = self.client.get("/api/v1/jobs/?page_size=50", name="jobs list").json()
            JobBoardUser.job_ids = [j["id"] for j in body.get("results", [])]

    @task(4)
    def board(self) -> None:
        self.client.get("/api/v1/jobs/?page_size=20", name="jobs list")

    @task(2)
    def search(self) -> None:
        self.client.get("/api/v1/jobs/?search=developer", name="jobs search")

    @task(3)
    def detail(self) -> None:
        if JobBoardUser.job_ids:
            job = JobBoardUser.job_ids[next(_ids) % len(JobBoardUser.job_ids)]
            self.client.get(f"/api/v1/jobs/{job}/", name="job detail")


class CandidateSubmitter(_Session):
    """One submission per user through the same API the apply wizard uses."""

    wait_time = between(1, 3)
    weight = 1
    done = False

    def on_start(self) -> None:
        self.email = f"load{next(_users):04d}@load.test"
        self.signed_in = self.sign_in(self.email)
        body = self.client.get(f"/api/v1/jobs/?search={JOB_TITLE}", name="jobs search").json()
        self.job_id = body["results"][0]["id"] if body.get("results") else None

    @task
    def apply(self) -> None:
        if self.done or not self.signed_in or not self.job_id:
            return
        h = self.csrf()
        app = self.client.post(
            "/api/v1/applications/", json={"job_id": self.job_id}, headers=h, name="start"
        )
        if app.status_code not in (200, 201):
            self.done = True
            return
        app_id = app.json()["id"]
        doc = self.client.post(
            "/api/v1/documents/direct-upload/",
            data={"purpose": "cv"},
            files={"file": ("synthetic_cv.pdf", CV_BYTES, "application/pdf")},
            headers=h,
            name="upload cv",
        )
        if doc.status_code not in (200, 201):
            self.done = True
            return
        self.client.put(
            f"/api/v1/applications/{app_id}/documents/",
            json={
                "documents": [
                    {"document_id": doc.json()["id"], "role": "cv", "required_doc_key": "cv"}
                ]
            },
            headers=h,
            name="attach cv",
        )
        questions = self.client.get(
            f"/api/v1/jobs/{self.job_id}/questions/", name="questions"
        ).json()
        answers = [self._answer(q) for q in questions]
        self.client.put(
            f"/api/v1/applications/{app_id}/answers/",
            json={"answers": [a for a in answers if a["value"] is not None]},
            headers=h,
            name="answers",
        )
        self.client.post(
            f"/api/v1/applications/{app_id}/submit/",
            json={"accept_privacy": True},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())},
            name="submit",
        )
        self.done = True

    @staticmethod
    def _answer(q: dict[str, Any]) -> dict[str, Any]:
        kind, options = q.get("type"), q.get("options") or []
        value: Any = "Built and maintained Django services with PostgreSQL."
        if kind == "yes_no":
            value = "yes"
        elif kind in ("number", "scale", "availability", "salary_expectation"):
            value = int((q.get("config") or {}).get("min") or 1)
        elif kind in ("single_choice", "dropdown") and options:
            value = options[0]["value"] if isinstance(options[0], dict) else options[0]
        elif kind in ("multi_choice", "multiple_choice") and options:
            value = [options[0]["value"] if isinstance(options[0], dict) else options[0]]
        elif kind == "file":
            value = None
        return {"key": q["key"], "value": value}


class HRReviewer(_Session):
    """The HR manager working through the applicants list."""

    wait_time = between(1, 2)
    weight = 1

    def on_start(self) -> None:
        self.sign_in(HR_EMAIL)
        me = self.client.get("/api/v1/me/", name="me").json()
        self.org = me.get("active_organisation_id") or (me.get("memberships") or [{}])[0].get(
            "organisation_id"
        )
        jobs = self.client.get(
            f"/api/v1/hr/jobs/?search={JOB_TITLE}", headers=self._org(), name="hr jobs"
        ).json()
        self.job_id = jobs["results"][0]["id"] if jobs.get("results") else None

    def _org(self) -> dict[str, str]:
        return {"X-Org-Id": str(self.org or "")}

    @task(3)
    def applicants(self) -> None:
        if self.job_id:
            self.client.get(
                f"/api/v1/hr/jobs/{self.job_id}/applications/",
                headers=self._org(),
                name="hr applicants",
            )

    @task(2)
    def filtered(self) -> None:
        if self.job_id:
            self.client.get(
                f"/api/v1/hr/jobs/{self.job_id}/applications/?band=recommended_for_review"
                "&ordering=-score",
                headers=self._org(),
                name="hr applicants filtered",
            )

    @task(1)
    def dashboard(self) -> None:
        self.client.get("/api/v1/hr/dashboard/summary/", headers=self._org(), name="hr dashboard")
