"""Organisation & team APIs - P02-T09."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.organisations.models import Department, Invitation, Membership, Organisation, Role
from apps.organisations.tests.factories import DepartmentFactory, make_org_with_team

pytestmark = pytest.mark.django_db
API = "/api/v1"


def client_for(user: Any) -> APIClient:
    c = APIClient()
    c.force_login(user)  # session auth, as the browser client uses (context middleware sees it)
    return c


# ---------------------------------------------------------------------------------- /me
class TestMe:
    def test_me_lists_memberships_and_mfa(self) -> None:
        team = make_org_with_team()
        body = client_for(team.hr_manager).get(f"{API}/me/").json()
        assert body["email"] == team.hr_manager.email and body["email_verified"] is True
        assert [(m["organisation_id"], m["role"]) for m in body["memberships"]] == [
            (str(team.org.pk), "hr_manager")
        ]
        assert body["mfa"]["required"] is True and body["mfa"]["in_grace"] is True
        assert body["platform_role"] == "none" and body["candidate_profile_id"] is None

    def test_active_org_from_header(self) -> None:
        team = make_org_with_team()
        c = client_for(team.recruiter)
        body = c.get(f"{API}/me/", HTTP_X_ORG_ID=str(team.org.pk)).json()
        assert body["active_organisation_id"] == str(team.org.pk)

    def test_patch_profile_normalises_phone_and_rejects_protected_fields(self) -> None:
        user = UserFactory()
        c = client_for(user)
        resp = c.patch(
            f"{API}/me/",
            {
                "preferred_name": "Tino",
                "phone_e164": "077 123 4567",
                "timezone": "Africa/Johannesburg",
            },
            format="json",
        )
        assert resp.status_code == 200, resp.content
        assert resp.json()["phone_e164"] == "+263771234567"
        assert AuditEvent.objects.filter(action="user.profile_updated").exists()
        bad = c.patch(
            f"{API}/me/", {"platform_role": "platform_admin", "email": "x@y.z"}, format="json"
        )
        assert bad.status_code == 400
        assert set(bad.json()["error"]["details"]) == {"platform_role", "email"}
        assert c.patch(f"{API}/me/", {"timezone": "Mars/Base"}, format="json").status_code == 400
        assert c.patch(f"{API}/me/", {"phone_e164": "12"}, format="json").status_code == 400
        assert c.patch(f"{API}/me/", {"locale": "fr"}, format="json").status_code == 400

    def test_requires_auth(self) -> None:
        assert APIClient().get(f"{API}/me/").status_code in (401, 403)


# ------------------------------------------------------------------------- organisations
class TestOrganisations:
    def test_create_org(self) -> None:
        user = UserFactory()
        resp = client_for(user).post(
            f"{API}/organisations/", {"name": "Zim Agro (Pvt) Ltd", "city": "Gweru"}, format="json"
        )
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["status"] == "pending_verification" and body["my_role"] == "org_admin"
        assert body["slug"] == "zim-agro-pvt-ltd"

    def test_create_requires_verified_email_and_rejects_status(self) -> None:
        unverified = UserFactory(verified=False)
        resp = client_for(unverified).post(f"{API}/organisations/", {"name": "X"}, format="json")
        assert resp.status_code == 403 and resp.json()["error"]["code"] == "email_unverified"
        resp = client_for(UserFactory()).post(
            f"{API}/organisations/", {"name": "X", "status": "active"}, format="json"
        )
        assert resp.status_code == 400 and "status" in resp.json()["error"]["details"]
        resp = client_for(UserFactory()).post(f"{API}/organisations/", {}, format="json")
        assert resp.status_code == 400 and "name" in resp.json()["error"]["details"]

    def test_retrieve_and_update_by_role(self) -> None:
        team = make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/"
        assert client_for(team.panelist).get(url).json()["my_role"] == "panelist"
        assert (
            client_for(team.hr_manager).patch(url, {"city": "Masvingo"}, format="json").status_code
            == 403
        )
        resp = client_for(team.admin).patch(
            url, {"city": "Masvingo", "description": "<p>Hi</p><img src=x>"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["city"] == "Masvingo" and resp.json()["description"] == "<p>Hi</p>"

    def test_policies_with_lock_version(self) -> None:
        team = make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/policies/"
        policy = client_for(team.hr_manager).get(url).json()
        assert policy["version"] == 1 and policy["llm_enabled"] is False
        assert client_for(team.recruiter).get(url).status_code == 403
        assert (
            client_for(team.hr_manager).patch(url, {"lock_version": 1}, format="json").status_code
            == 403
        )
        admin = client_for(team.admin)
        assert admin.patch(url, {"retention_months": 18}, format="json").status_code == 400
        ok = admin.patch(url, {"retention_months": 18, "lock_version": 1}, format="json")
        assert ok.status_code == 200 and ok.json()["version"] == 2
        stale = admin.patch(url, {"retention_months": 6, "lock_version": 1}, format="json")
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "conflict.stale_version"


# ------------------------------------------------------------------------------ structure
class TestStructure:
    def test_department_crud_and_audit(self) -> None:
        team = make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/departments/"
        hr = client_for(team.hr_manager)
        created = hr.post(url, {"name": "Engineering"}, format="json")
        assert created.status_code == 201
        dep_id = created.json()["id"]
        dup = hr.post(url, {"name": "engineering"}, format="json")
        assert dup.status_code == 400 and "name" in dup.json()["error"]["details"]
        assert client_for(team.panelist).get(url).json()["count"] == 1  # all staff can view
        assert (
            client_for(team.recruiter).post(url, {"name": "Ops"}, format="json").status_code == 403
        )
        assert hr.patch(f"{url}{dep_id}/", {"name": "Eng"}, format="json").json()["name"] == "Eng"
        assert hr.delete(f"{url}{dep_id}/").status_code == 204
        actions = set(AuditEvent.objects.values_list("action", flat=True))
        assert {"department.created", "department.updated", "department.deleted"} <= actions

    def test_location_create_rejects_organisation_field(self) -> None:
        team, other = make_org_with_team(), make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/locations/"
        resp = client_for(team.admin).post(
            url, {"name": "HQ", "city": "Harare", "organisation": str(other.org.pk)}, format="json"
        )
        assert resp.status_code == 400  # unknown field rejected outright
        ok = client_for(team.admin).post(
            url, {"name": "HQ", "city": "Harare", "workplace_type_default": "hybrid"}, format="json"
        )
        assert ok.status_code == 201


# -------------------------------------------------------------------------------- members
class TestMembers:
    def test_list_change_role_deactivate_reset_mfa(self) -> None:
        team = make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/members/"
        listing = client_for(team.hr_manager).get(url).json()
        assert listing["count"] == 6
        assert client_for(team.recruiter).get(url).status_code == 403
        target = Membership.objects.for_org(team.org).get(user=team.panelist)
        admin = client_for(team.admin)
        assert (
            client_for(team.hr_manager)
            .patch(f"{url}{target.pk}/", {"role": "auditor"}, format="json")
            .status_code
            == 403
        )
        changed = admin.patch(
            f"{url}{target.pk}/", {"role": "auditor", "reason": "audit duty"}, format="json"
        )
        assert changed.status_code == 200 and changed.json()["role"] == "auditor"
        assert admin.patch(f"{url}{target.pk}/", {"role": "god"}, format="json").status_code == 400
        gone = admin.delete(f"{url}{target.pk}/")
        assert gone.status_code == 200 and gone.json()["membership"]["status"] == "deactivated"
        assert "needs_reassignment" in gone.json()
        reset = admin.post(
            f"{url}{target.pk}/reset-mfa/", {"reason": "Lost phone, verified by HR"}, format="json"
        )
        assert reset.status_code == 200
        assert (
            admin.post(f"{url}{target.pk}/reset-mfa/", {"reason": "x"}, format="json").status_code
            == 400
        )

    def test_last_admin_guard_via_api(self) -> None:
        team = make_org_with_team()
        me = Membership.objects.for_org(team.org).get(user=team.admin)
        url = f"{API}/organisations/{team.org.pk}/members/{me.pk}/"
        resp = client_for(team.admin).patch(url, {"role": "recruiter"}, format="json")
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "conflict.last_admin"
        assert client_for(team.admin).delete(url).status_code == 409


# ---------------------------------------------------------------------------- invitations
class TestInvitations:
    def test_full_invitation_journey(self, django_capture_on_commit_callbacks: Any) -> None:
        team = make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/invitations/"
        admin = client_for(team.admin)
        with django_capture_on_commit_callbacks(execute=True):
            resp = admin.post(
                url, {"email": "chipo@example.test", "role": "recruiter"}, format="json"
            )
        assert resp.status_code == 201
        assert "token" not in resp.json() and "token_hash" not in resp.json()
        token = re.search(r"/invitations/([A-Za-z0-9_\-]+)", mail.outbox[-1].body).group(1)  # type: ignore[union-attr]

        preview = APIClient().get(f"{API}/invitations/{token}/")
        assert preview.status_code == 200
        assert preview.json()["organisation_name"] == team.org.name
        assert preview.json()["email_hint"] == "ch***@example.test"

        invitee = UserFactory(email="chipo@example.test")
        assert APIClient().post(f"{API}/invitations/{token}/accept/").status_code in (401, 403)
        accepted = client_for(invitee).post(f"{API}/invitations/{token}/accept/")
        assert accepted.status_code == 201 and accepted.json()["role"] == "recruiter"
        again = client_for(invitee).post(f"{API}/invitations/{token}/accept/")
        assert again.status_code == 410 and again.json()["error"]["code"] == "invitation_accepted"
        assert APIClient().get(f"{API}/invitations/nonsense/").status_code == 404

    def test_list_resend_revoke_and_permissions(self) -> None:
        team = make_org_with_team()
        url = f"{API}/organisations/{team.org.pk}/invitations/"
        admin = client_for(team.admin)
        inv_id = admin.post(
            url, {"email": "a@example.test", "role": "auditor"}, format="json"
        ).json()["id"]
        assert client_for(team.hr_manager).get(url).status_code == 403
        assert admin.get(url, {"status": "pending"}).json()["count"] == 1
        assert admin.post(f"{url}{inv_id}/resend/").status_code == 200
        revoked = admin.delete(f"{url}{inv_id}/")
        assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
        assert admin.get(url, {"status": "pending"}).json()["count"] == 0
        dup = admin.post(url, {"email": team.recruiter.email, "role": "auditor"}, format="json")
        assert dup.status_code == 409 and dup.json()["error"]["code"] == "already_member"
        assert (
            admin.post(url, {"email": "bad", "role": "auditor"}, format="json").status_code == 400
        )
        assert Invitation.objects.unscoped().count() == 1


# --------------------------------------------------------------------------------- public
def test_public_company_profile_only_for_active_orgs() -> None:
    team = make_org_with_team()
    body = APIClient().get(f"{API}/companies/{team.org.slug}/").json()
    assert body["name"] == team.org.name and body["open_jobs"] == []
    assert "settings" not in body and "registration_number" not in body
    for status in (Organisation.Status.SUSPENDED, Organisation.Status.PENDING_VERIFICATION):
        hidden = make_org_with_team(status=status)
        assert APIClient().get(f"{API}/companies/{hidden.org.slug}/").status_code == 404


def test_department_names_unique_per_org_case_insensitive() -> None:
    team = make_org_with_team()
    DepartmentFactory(organisation=team.org, name="Finance")
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        Department.objects.create(organisation=team.org, name="FINANCE")
    DepartmentFactory(organisation=make_org_with_team().org, name="Finance")  # other org fine
    assert Role.ORG_ADMIN in Role.values
