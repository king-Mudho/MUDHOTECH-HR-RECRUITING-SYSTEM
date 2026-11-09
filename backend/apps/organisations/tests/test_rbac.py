"""RBAC matrix and permission classes - P02-T08 (EC-ACC-09/10 hook)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import PlatformRole
from apps.accounts.tests.factories import UserFactory
from apps.audit.models import AuditEvent
from apps.core.exceptions import NotFoundError, OrgSuspendedError, PermissionDeniedError
from apps.organisations import permissions as perms
from apps.organisations import rbac
from apps.organisations.models import Membership, Organisation, Role
from apps.organisations.tests.factories import make_org_with_team

pytestmark = pytest.mark.django_db


def drf_request(user: Any, method: str = "get") -> Request:
    raw = getattr(APIRequestFactory(), method)("/x")
    force_authenticate(raw, user=user)
    req = Request(raw)
    req.user = user
    return req


def view(**kwargs: Any) -> Any:
    return SimpleNamespace(kwargs=kwargs)


def test_matrix_is_consistent() -> None:
    for action, roles in rbac.ORG_ACTIONS.items():
        assert roles, action
        assert roles <= set(Role.values), action
    assert rbac.can("org_admin", "members.manage")
    assert not rbac.can("recruiter", "members.manage")
    assert not rbac.can(None, "org.view")
    assert "members.manage" in rbac.actions_for("org_admin")
    with pytest.raises(KeyError):
        rbac.roles_for("members.manag")  # typo fails closed


@pytest.mark.parametrize("role", Role.values)
def test_has_org_action_follows_matrix(role: str) -> None:
    team = make_org_with_team()
    user = team.user_for(role)
    permission = perms.HasOrgAction("members.manage")()
    if role in rbac.roles_for("members.manage"):
        assert permission.has_permission(
            drf_request(user, "post"), view(organisation_id=team.org.pk)
        )
    else:
        with pytest.raises(PermissionDeniedError) as exc:
            permission.has_permission(drf_request(user, "post"), view(organisation_id=team.org.pk))
        assert exc.value.status_code == 403


def test_non_member_gets_404_not_403() -> None:
    mine, theirs = make_org_with_team(), make_org_with_team()
    with pytest.raises(NotFoundError):
        perms.HasOrgRole(Role.ORG_ADMIN)().has_permission(
            drf_request(mine.admin), view(organisation_id=theirs.org.pk)
        )


def test_context_membership_used_without_path_kwarg() -> None:
    team = make_org_with_team()
    req = drf_request(team.recruiter)
    with pytest.raises(PermissionDeniedError) as exc:
        perms.HasOrgRole(Role.RECRUITER)().has_permission(req, view())
    assert exc.value.details == {"reason": "org_context_required"}
    req.membership = Membership.objects.for_org(team.org).get(user=team.recruiter)
    assert perms.HasOrgRole(Role.RECRUITER)().has_permission(req, view())


def test_unauthenticated_is_401() -> None:
    from django.contrib.auth.models import AnonymousUser

    with pytest.raises(PermissionDeniedError) as exc:
        perms.HasOrgRole(Role.RECRUITER)().has_permission(drf_request(AnonymousUser()), view())
    assert exc.value.status_code == 401


def test_suspended_org_blocks_writes_but_not_reads() -> None:
    team = make_org_with_team(status=Organisation.Status.SUSPENDED)
    permission = perms.HasOrgRole(Role.ORG_ADMIN)()
    assert permission.has_permission(drf_request(team.admin), view(organisation_id=team.org.pk))
    with pytest.raises(OrgSuspendedError):
        permission.has_permission(
            drf_request(team.admin, "patch"), view(organisation_id=team.org.pk)
        )


def test_has_org_role_rejects_unknown_roles() -> None:
    with pytest.raises(ValueError):
        perms.HasOrgRole("superuser")


class TestIsAssignedToJob:
    def _req(self, team: Any, user: Any) -> Request:
        req = drf_request(user)
        req.membership = Membership.objects.for_org(team.org).get(user=user)
        return req

    def test_admin_hr_see_all_others_need_assignment(self) -> None:
        team = make_org_with_team()
        job = SimpleNamespace(organisation_id=team.org.pk, pk=uuid.uuid4())
        p = perms.IsAssignedToJob()
        assert p.has_object_permission(self._req(team, team.hr_manager), view(), job)
        assert not p.has_object_permission(self._req(team, team.recruiter), view(), job)
        old = perms._assignment_checker
        perms.register_assignment_checker(lambda m, j: m.role == Role.RECRUITER)
        try:
            assert p.has_object_permission(self._req(team, team.recruiter), view(), job)
            app = SimpleNamespace(job=job)  # objects carrying .job are resolved to the job
            assert p.has_object_permission(self._req(team, team.recruiter), view(), app)
        finally:
            perms._assignment_checker = old

    def test_other_org_job_is_404(self) -> None:
        team, other = make_org_with_team(), make_org_with_team()
        with pytest.raises(NotFoundError):
            perms.IsAssignedToJob().has_object_permission(
                self._req(team, team.admin),
                view(),
                SimpleNamespace(organisation_id=other.org.pk),
            )


@pytest.mark.parametrize(
    ("role", "method", "admin_ok", "staff_ok"),
    [
        (PlatformRole.PLATFORM_ADMIN, "post", True, True),
        (PlatformRole.PLATFORM_SUPPORT, "get", False, True),
        (PlatformRole.PLATFORM_SUPPORT, "post", False, False),
        (PlatformRole.NONE, "get", False, False),
    ],
)
def test_platform_permissions(role: str, method: str, admin_ok: bool, staff_ok: bool) -> None:
    user = UserFactory(platform_role=role)
    req = drf_request(user, method)
    assert perms.IsPlatformAdmin().has_permission(req, view()) is admin_ok
    assert perms.IsPlatformStaff().has_permission(req, view()) is staff_ok


def test_candidate_owner() -> None:
    me, other = UserFactory(), UserFactory()
    p = perms.IsCandidateOwner()
    assert p.has_permission(drf_request(me), view())
    assert p.has_object_permission(
        drf_request(me), view(), SimpleNamespace(candidate_user_id=me.pk)
    )
    assert p.has_object_permission(drf_request(me), view(), SimpleNamespace(user_id=me.pk))
    with pytest.raises(NotFoundError):
        p.has_object_permission(
            drf_request(me), view(), SimpleNamespace(candidate_user_id=other.pk)
        )


def test_conflict_of_interest_blocks_own_application_and_audits() -> None:
    """EC-ACC-09 / EC-ACC-10: staff member who is also the applicant."""
    team = make_org_with_team()
    membership = Membership.objects.for_org(team.org).get(user=team.recruiter)
    own = SimpleNamespace(candidate_user_id=team.recruiter.pk)
    someone_else = SimpleNamespace(candidate_user_id=team.panelist.pk)
    perms.assert_no_conflict_of_interest(drf_request(team.recruiter), membership, someone_else)
    with pytest.raises(PermissionDeniedError) as exc:
        perms.assert_no_conflict_of_interest(drf_request(team.recruiter), membership, own)
    assert exc.value.code == "conflict_of_interest"
    event = AuditEvent.objects.get(action="conflict_of_interest_blocked")
    assert event.organisation_id == team.org.pk and event.reason == "staff member is the applicant"
