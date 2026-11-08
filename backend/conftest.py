"""Project-wide pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db: Any) -> Any:
    from apps.accounts.models import User

    return User.objects.create_user(email="user@example.test", password="Str0ng-Passw0rd!")


@pytest.fixture
def org(db: Any) -> Any:
    from apps.organisations.models import Organisation

    return Organisation.objects.create(name="MudhoTech Demo Ltd", slug="mudhotech-demo")


@pytest.fixture
def other_org(db: Any) -> Any:
    from apps.organisations.models import Organisation

    return Organisation.objects.create(name="Acme Mining Zimbabwe", slug="acme-mining")


@pytest.fixture
def tenant_guard() -> Iterator[None]:
    """Simulate being inside an HTTP request (strict tenant guard active)."""
    from apps.core.context import tenant_guard_var

    token = tenant_guard_var.set(True)
    yield
    tenant_guard_var.reset(token)
