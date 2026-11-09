"""factory_boy factories for organisations (synthetic data only)."""

from __future__ import annotations

from dataclasses import dataclass

import factory

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.organisations.models import (
    Department,
    Location,
    Membership,
    Organisation,
    OrganisationPolicy,
    Role,
)


class OrganisationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organisation
        skip_postgeneration_save = True

    name = factory.Sequence(lambda n: f"Synthetic Employer {n} (Pvt) Ltd")
    slug = factory.Sequence(lambda n: f"synthetic-employer-{n}")
    status = Organisation.Status.ACTIVE
    city = "Harare"

    @factory.post_generation
    def policy(self, create: bool, extracted: object, **kwargs: object) -> None:
        if create:
            OrganisationPolicy.objects.get_or_create(organisation=self)


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    organisation = factory.SubFactory(OrganisationFactory)
    user = factory.SubFactory(UserFactory)
    role = Role.RECRUITER


class DepartmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Department

    organisation = factory.SubFactory(OrganisationFactory)
    name = factory.Sequence(lambda n: f"Department {n}")


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    organisation = factory.SubFactory(OrganisationFactory)
    name = factory.Sequence(lambda n: f"Office {n}")
    city = "Harare"


@dataclass
class OrgTeam:
    org: Organisation
    admin: User
    hr_manager: User
    recruiter: User
    hiring_manager: User
    panelist: User
    auditor: User

    def user_for(self, role: str) -> User:
        return getattr(self, "admin" if role == Role.ORG_ADMIN else role)  # type: ignore[no-any-return]


def make_org_with_team(**org_kwargs: object) -> OrgTeam:
    """docs/09 §3 helper: an active org with one member per role."""
    org = OrganisationFactory(**org_kwargs)
    users = {}
    for role in Role.values:
        user = UserFactory()
        MembershipFactory(organisation=org, user=user, role=role)
        users[role] = user
    return OrgTeam(
        org=org,
        admin=users[Role.ORG_ADMIN],
        hr_manager=users[Role.HR_MANAGER],
        recruiter=users[Role.RECRUITER],
        hiring_manager=users[Role.HIRING_MANAGER],
        panelist=users[Role.PANELIST],
        auditor=users[Role.AUDITOR],
    )
