from typing import Any

import pytest
from django.db import IntegrityError

from apps.accounts.models import User, normalize_email_address
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organisations.tests.factories import OrganisationFactory

pytestmark = pytest.mark.django_db


def test_email_is_normalised_and_unique_case_insensitively() -> None:
    user = User.objects.create_user(email="  Tendai.M@Example.TEST ", password="x" * 12)
    assert user.email == "tendai.m@example.test"
    with pytest.raises(IntegrityError):
        User.objects.create(email="TENDAI.M@example.test")


def test_natural_key_lookup_is_case_insensitive() -> None:
    UserFactory(email="chipo@example.test")
    assert User.objects.get_by_natural_key("CHIPO@example.test").email == "chipo@example.test"


def test_create_superuser_flags() -> None:
    admin = User.objects.create_superuser(email="root@example.test", password="x" * 12)
    assert admin.is_staff and admin.is_superuser
    with pytest.raises(ValueError):
        User.objects.create_superuser(email="bad@example.test", password="x", is_staff=False)
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="x")


def test_factory_password_and_full_name(client: Any) -> None:
    user = UserFactory(first_name="Rudo", last_name="Moyo")
    assert user.check_password(DEFAULT_PASSWORD)
    assert user.full_name == "Rudo Moyo"
    assert str(user) == user.email
    user.email = " MIXED@Case.Test "
    user.clean()
    assert user.email == normalize_email_address(" MIXED@Case.Test ")


def test_organisation_factory() -> None:
    org = OrganisationFactory()
    assert org.status == "active"
    assert str(org) == org.name
