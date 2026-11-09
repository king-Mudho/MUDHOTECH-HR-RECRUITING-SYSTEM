from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import identify_hasher, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import override_settings

from apps.accounts.models import PlatformRole
from apps.accounts.password_validation import BreachedPasswordValidator
from apps.accounts.tests.factories import UserFactory
from apps.core import time

pytestmark = pytest.mark.django_db


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.Argon2PasswordHasher"])
def test_argon2_is_the_hasher() -> None:
    assert identify_hasher(make_password("x" * 12)).algorithm == "argon2"


def test_production_hasher_order() -> None:
    from config.settings import base

    assert base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")


@pytest.mark.parametrize("pw", ["password123", "PASSWORD123", "qwertyuiop", "1234567890"])
def test_breached_passwords_rejected(pw: str) -> None:
    with pytest.raises(ValidationError) as exc:
        BreachedPasswordValidator().validate(pw)
    assert exc.value.error_list[0].code == "password_breached"


def test_strong_password_accepted_without_composition_rules() -> None:
    # Long passphrase with no digits/symbols is fine (no composition rules, FR-M01-06).
    validate_password("correct horse battery staple tendai")


def test_min_length_ten() -> None:
    with pytest.raises(ValidationError):
        validate_password("Zx9!kLm2q")  # 9 chars


def test_validator_help_text() -> None:
    assert "breached" in BreachedPasswordValidator().get_help_text()


def test_user_profile_fields_and_platform_role() -> None:
    user = UserFactory(
        preferred_name="Tino", first_name="Tinotenda", last_name="Moyo", verified=False
    )
    assert user.display_name == "Tino"
    assert user.locale == "en" and user.timezone == "Africa/Harare"
    assert user.platform_role == PlatformRole.NONE and not user.is_platform_staff
    assert not user.is_email_verified
    user.platform_role = PlatformRole.PLATFORM_SUPPORT
    assert user.is_platform_staff


def test_save_normalises_email() -> None:
    user = UserFactory()
    user.email = "  New.Address@Example.TEST "
    user.save()
    user.refresh_from_db()
    assert user.email == "new.address@example.test"


def test_mfa_grace_is_started_once() -> None:
    user = UserFactory()
    assert user.mfa_grace_deadline is None
    user.start_mfa_grace()
    first = user.mfa_grace_started_at
    assert first is not None
    user.start_mfa_grace()
    assert user.mfa_grace_started_at == first
    assert user.mfa_grace_deadline == first + timedelta(days=7)
    assert user.mfa_grace_deadline > time.now()


def test_build_breached_passwords_command(tmp_path: Any) -> None:
    from io import StringIO

    from django.core.management import call_command

    src = tmp_path / "list.txt"
    src.write_text("hunter2hunter2\nsunshine\n\n", encoding="utf-8")
    out = tmp_path / "out.sha1.gz"
    call_command(
        "build_breached_passwords", "--source", str(src), "--output", str(out), stdout=StringIO()
    )
    validator = BreachedPasswordValidator(path=str(out))
    with pytest.raises(ValidationError):
        validator.validate("hunter2hunter2")
    validator.validate("password123")  # not in this custom list
