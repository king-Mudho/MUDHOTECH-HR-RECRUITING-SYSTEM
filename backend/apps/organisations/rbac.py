"""Central role x action matrix (SRS §2, FR-M03). The single source of truth for org permissions.

Views declare the *action* they perform (``HasOrgAction("members.manage")``); this table decides
which membership roles may perform it. ``tests/permissions/matrix.py`` asserts endpoints honour it.
Later phases add their actions here (jobs, applications, shortlists...).
"""

from __future__ import annotations

from .models import Role

ALL_STAFF = frozenset(Role.values)
ADMIN = frozenset({Role.ORG_ADMIN})
ADMIN_HR = frozenset({Role.ORG_ADMIN, Role.HR_MANAGER})
RECRUITING = frozenset({Role.ORG_ADMIN, Role.HR_MANAGER, Role.RECRUITER})

ORG_ACTIONS: dict[str, frozenset[str]] = {
    # organisation profile & policies
    "org.view": ALL_STAFF,
    "org.update": ADMIN,
    "policy.view": ADMIN_HR,
    "policy.update": ADMIN,
    # structure
    "structure.view": ALL_STAFF,
    "structure.manage": ADMIN_HR,
    "taxonomy.manage": ADMIN_HR,
    # team
    "members.view": ADMIN_HR,
    "members.manage": ADMIN,
    "invitations.manage": ADMIN,
    "members.reset_mfa": ADMIN,
    # governance (UI in Phase 08)
    "audit.view": frozenset({Role.ORG_ADMIN, Role.AUDITOR}),
    # recruiting (enforced from Phase 03 on; declared here so the matrix is complete)
    "jobs.view": ALL_STAFF - {Role.PANELIST},
    "jobs.create": RECRUITING,
    "jobs.approve": ADMIN_HR,
    "jobs.publish": ADMIN_HR,
    "questions.protected_exception": ADMIN_HR,
    "applications.view": RECRUITING | {Role.HIRING_MANAGER},
    "applications.transition": RECRUITING,
    "shortlist.propose": RECRUITING,
    "shortlist.approve": ADMIN_HR,
}


def roles_for(action: str) -> frozenset[str]:
    try:
        return ORG_ACTIONS[action]
    except KeyError as exc:  # fail closed on typos
        raise KeyError(f"Unknown RBAC action '{action}' - declare it in rbac.ORG_ACTIONS") from exc


def can(role: str | None, action: str) -> bool:
    return role is not None and role in roles_for(action)


def actions_for(role: str) -> list[str]:
    return sorted(a for a, roles in ORG_ACTIONS.items() if role in roles)
