"""Organisation/team/invitation services - P02-T06 (EC-ORG-01..05, EC-ORG-09, EC-ACC-12)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from django.core import mail
from django.test import Client

from apps.accounts import mfa
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.audit.models import AuditEvent
from apps.core import time
from apps.core.exceptions import StaleVersionError
from apps.organisations import services
from apps.organisations.models import Invitation, Membership, Organisation, Role
from apps.organisations.tests.factories import MembershipFactory, make_org_with_team

pytestmark = pytest.mark.django_db


@pytest.fixture
def commit(django_capture_on_commit_callbacks: Any) -> Any:
    def run(fn: Any) -> Any:
        with django_capture_on_commit_callbacks(execute=True):
            return fn()

    return run


# --------------------------------------------------------------------------- organisations
def test_create_organisation_makes_creator_admin_and_pending(commit: Any) -> None:
    user = UserFactory()
    org = services.create_organisation(
        user=user,
        data={
            "name": "Acme Mining Zimbabwe",
            "city": "Bulawayo",
            "description": "<p>We mine.</p><script>alert(1)</script>",
            "status": "active",
        },
    )
    assert org.status == Organisation.Status.PENDING_VERIFICATION  # client cannot set status
    assert org.slug == "acme-mining-zimbabwe"
    assert org.description == "<p>We mine.</p>"
    assert org.policy.retention_months == 12 and org.policy.blind_review_default
    m = Membership.objects.for_org(org).get(user=user)
    assert m.role == Role.ORG_ADMIN
    assert mfa.mfa_status(user).required  # org_admin must use MFA
    assert AuditEvent.objects.filter(action="organisation.created", target_id=str(org.pk)).exists()


def test_same_name_gets_deduplicated_slug() -> None:
    """EC-ORG-01."""
    a = services.create_organisation(user=UserFactory(), data={"name": "Acme"})
    b = services.create_organisation(user=UserFactory(), data={"name": "Acme"})
    c = services.create_organisation(user=UserFactory(), data={"name": "ACME!"})
    assert (a.slug, b.slug, c.slug) == ("acme", "acme-2", "acme-3")


def test_update_organisation_audits_before_after() -> None:
    team = make_org_with_team()
    services.update_organisation(
        org=team.org,
        actor=team.admin,
        data={"city": "Mutare", "slug": "hijack", "status": "active"},
    )
    team.org.refresh_from_db()
    assert team.org.city == "Mutare" and team.org.slug != "hijack"
    event = AuditEvent.objects.get(action="organisation.updated")
    assert event.before == {"city": "Harare"} and event.after == {"city": "Mutare"}


def test_policy_optimistic_lock() -> None:
    team = make_org_with_team()
    policy = services.update_policy(
        org=team.org, actor=team.admin, data={"retention_months": 24}, lock_version=1
    )
    assert policy.version == 2 and policy.retention_months == 24
    with pytest.raises(StaleVersionError) as exc:
        services.update_policy(
            org=team.org, actor=team.admin, data={"retention_months": 6}, lock_version=1
        )
    assert exc.value.details == {"current_version": 2}


# ----------------------------------------------------------------------------- invitations
def _token_from_mail() -> str:
    match = re.search(r"/invitations/([A-Za-z0-9_\-]+)", mail.outbox[-1].body)
    assert match
    return match.group(1)


def test_invite_and_accept_flow(commit: Any) -> None:
    team = make_org_with_team()
    issued = commit(
        lambda: services.invite_member(
            org=team.org, actor=team.admin, email=" New.Hire@Example.TEST ", role=Role.HR_MANAGER
        )
    )
    inv = issued.invitation
    assert inv.email == "new.hire@example.test" and inv.status == Invitation.Status.PENDING
    assert (
        inv.token_hash == services.hash_token(issued.token) and issued.token not in inv.token_hash
    )
    assert mail.outbox[-1].to == ["new.hire@example.test"]
    assert _token_from_mail() == issued.token

    invitee = UserFactory(email="new.hire@example.test")
    membership = services.accept_invitation(token=issued.token, user=invitee)
    assert membership.role == Role.HR_MANAGER and membership.invited_by == team.admin
    inv.refresh_from_db()
    assert inv.status == Invitation.Status.ACCEPTED
    assert mfa.mfa_status(invitee).required  # hr_manager -> MFA grace starts
    created = AuditEvent.objects.get(action="invitation.created")
    assert created.after["email"] == "new.hire@example.test" and "token" not in str(created.after)


def test_invitation_to_existing_member_rejected() -> None:
    """EC-ORG-03."""
    team = make_org_with_team()
    with pytest.raises(services.AlreadyMemberError) as exc:
        services.invite_member(
            org=team.org, actor=team.admin, email=team.recruiter.email.upper(), role=Role.AUDITOR
        )
    assert exc.value.code == "already_member"


@pytest.mark.parametrize("state", ["expired", "revoked", "accepted"])
def test_invitation_expired_revoked_reused(state: str) -> None:
    """EC-ORG-04: clear message, token single-use."""
    team = make_org_with_team()
    issued = services.invite_member(
        org=team.org, actor=team.admin, email="x@example.test", role=Role.RECRUITER
    )
    invitee = UserFactory(email="x@example.test")
    if state == "expired":
        Invitation.objects.unscoped().filter(pk=issued.invitation.pk).update(
            expires_at=time.now() - timedelta(seconds=1)
        )
    elif state == "revoked":
        services.revoke_invitation(invitation=issued.invitation, actor=team.admin)
    else:
        services.accept_invitation(token=issued.token, user=invitee)
    with pytest.raises(services.InvitationGoneError) as exc:
        services.accept_invitation(token=issued.token, user=invitee)
    assert exc.value.code == f"invitation_{state}" and exc.value.status_code == 410


def test_unknown_token_is_404() -> None:
    with pytest.raises(services.NotFoundError):
        services.accept_invitation(token="nope", user=UserFactory())


def test_accept_requires_matching_verified_email() -> None:
    """EC-ORG-05."""
    team = make_org_with_team()
    issued = services.invite_member(
        org=team.org, actor=team.admin, email="invited@example.test", role=Role.RECRUITER
    )
    with pytest.raises(services.InvitationEmailMismatchError):
        services.accept_invitation(token=issued.token, user=UserFactory(email="other@example.test"))
    unverified = UserFactory(email="invited@example.test", verified=False)
    with pytest.raises(services.InvitationEmailMismatchError):
        services.accept_invitation(token=issued.token, user=unverified)

    allowed = services.invite_member(
        org=team.org,
        actor=team.admin,
        email="alias@example.test",
        role=Role.RECRUITER,
        allow_any_email=True,
    )
    m = services.accept_invitation(token=allowed.token, user=UserFactory(email="real@example.test"))
    assert m.is_active


def test_resend_rotates_token_and_reinvite_replaces_open_invitation() -> None:
    team = make_org_with_team()
    first = services.invite_member(
        org=team.org, actor=team.admin, email="r@example.test", role=Role.RECRUITER
    )
    resent = services.resend_invitation(invitation=first.invitation, actor=team.admin)
    assert resent.token != first.token
    with pytest.raises(services.NotFoundError):
        services.get_invitation_by_token(first.token)  # old link dead
    again = services.invite_member(
        org=team.org, actor=team.admin, email="r@example.test", role=Role.AUDITOR
    )
    first.invitation.refresh_from_db()
    assert first.invitation.status == Invitation.Status.REVOKED
    assert again.invitation.role == Role.AUDITOR
    with pytest.raises(services.InvitationGoneError):
        services.resend_invitation(invitation=first.invitation, actor=team.admin)


def test_rejoin_after_deactivation_via_invitation() -> None:
    team = make_org_with_team()
    services.deactivate_member(
        membership=Membership.objects.for_org(team.org).get(user=team.panelist), actor=team.admin
    )
    issued = services.invite_member(
        org=team.org, actor=team.admin, email=team.panelist.email, role=Role.RECRUITER
    )
    m = services.accept_invitation(token=issued.token, user=team.panelist)
    assert m.is_active and m.role == Role.RECRUITER


# ----------------------------------------------------------------------------- memberships
def test_last_admin_cannot_be_demoted_or_deactivated() -> None:
    """EC-ORG-02."""
    team = make_org_with_team()
    admin_m = Membership.objects.for_org(team.org).get(user=team.admin)
    with pytest.raises(services.LastAdminError) as exc:
        services.change_role(membership=admin_m, actor=team.admin, role=Role.RECRUITER)
    assert exc.value.code == "conflict.last_admin" and exc.value.status_code == 409
    with pytest.raises(services.LastAdminError):
        services.deactivate_member(membership=admin_m, actor=team.admin)
    # With a second admin it is allowed.
    MembershipFactory(organisation=team.org, role=Role.ORG_ADMIN)
    services.change_role(membership=admin_m, actor=team.admin, role=Role.HR_MANAGER, reason="moved")
    admin_m.refresh_from_db()
    assert admin_m.role == Role.HR_MANAGER
    event = AuditEvent.objects.get(action="membership.role_changed")
    assert event.before == {"role": "org_admin"} and event.reason == "moved"


def test_change_role_to_same_is_noop_and_privileged_starts_grace() -> None:
    team = make_org_with_team()
    m = Membership.objects.for_org(team.org).get(user=team.recruiter)
    services.change_role(membership=m, actor=team.admin, role=Role.RECRUITER)
    assert not AuditEvent.objects.filter(action="membership.role_changed").exists()
    services.change_role(membership=m, actor=team.admin, role=Role.HR_MANAGER)
    team.recruiter.refresh_from_db()
    assert team.recruiter.mfa_grace_started_at is not None


def test_deactivation_revokes_sessions_and_lists_reassignments() -> None:
    """EC-ACC-12, EC-ORG-09 (provider hook; jobs register in Phase 03)."""
    team = make_org_with_team()
    client = Client()
    client.post(
        "/api/v1/auth/browser/v1/auth/login",
        {"email": team.recruiter.email, "password": DEFAULT_PASSWORD},
        content_type="application/json",
    )
    assert client.get("/api/v1/auth/browser/v1/auth/session").status_code == 200

    def provider(m: Membership) -> list[dict[str, Any]]:
        return [{"type": "job", "id": "J-1", "title": "Software Developer"}]

    services.register_reassignment_provider(provider)
    try:
        m = Membership.objects.for_org(team.org).get(user=team.recruiter)
        result = services.deactivate_member(membership=m, actor=team.admin, reason="left company")
    finally:
        services._REASSIGNMENT_PROVIDERS.remove(provider)
    assert result.sessions_revoked == 1
    assert result.needs_reassignment == [
        {"type": "job", "id": "J-1", "title": "Software Developer"}
    ]
    assert client.get("/api/v1/auth/browser/v1/auth/session").status_code == 401
    again = services.deactivate_member(membership=result.membership, actor=team.admin)
    assert again.sessions_revoked == 0  # idempotent


def test_privileged_provider_ignores_inactive_memberships() -> None:
    team = make_org_with_team()
    m = Membership.objects.for_org(team.org).get(user=team.hr_manager)
    assert services.user_has_privileged_membership(team.hr_manager)
    services.deactivate_member(membership=m, actor=team.admin)
    assert not services.user_has_privileged_membership(team.hr_manager)
    assert not services.user_has_privileged_membership(team.recruiter)


@pytest.mark.parametrize(
    ("status", "verified", "error"),
    [
        (Organisation.Status.PENDING_VERIFICATION, False, "org_unverified"),
        (Organisation.Status.ACTIVE, False, "org_unverified"),
        (Organisation.Status.SUSPENDED, True, "org_suspended"),
        (Organisation.Status.CLOSED, True, "org_suspended"),
        (Organisation.Status.ACTIVE, True, None),
    ],
)
def test_publish_eligibility_guard(status: str, verified: bool, error: str | None) -> None:
    """EC-ORG-08: unverified orgs may draft but not publish (D-01)."""
    team = make_org_with_team(status=status)
    team.org.verified_at = time.now() if verified else None
    if error is None:
        services.assert_can_publish(team.org)
        return
    with pytest.raises(services.DomainError) as exc:
        services.assert_can_publish(team.org)
    assert exc.value.code == error
