from typing import Any

import pytest
from django.db.models import Count
from django.test import override_settings

from apps.core.models import UnscopedTenantQueryError
from tests.core_testapp.models import Widget

pytestmark = pytest.mark.django_db


@pytest.fixture
def widgets(org: Any, other_org: Any) -> None:
    Widget.objects.create(organisation=org, name="a1")
    Widget.objects.create(organisation=org, name="a2")
    Widget.objects.create(organisation=other_org, name="b1")


def test_for_org_scopes_rows(widgets: None, org: Any, other_org: Any) -> None:
    assert sorted(Widget.objects.for_org(org).values_list("name", flat=True)) == ["a1", "a2"]
    assert list(Widget.objects.for_org(other_org.pk).values_list("name", flat=True)) == ["b1"]
    assert Widget.objects.for_org(org).filter(name="b1").count() == 0


def test_for_org_requires_org() -> None:
    with pytest.raises(ValueError):
        Widget.objects.for_org(None)  # type: ignore[arg-type]


def test_unscoped_query_outside_request_is_allowed(widgets: None) -> None:
    assert Widget.objects.count() == 3


@pytest.mark.usefixtures("tenant_guard", "widgets")
class TestStrictGuard:
    def test_iteration_raises(self) -> None:
        with pytest.raises(UnscopedTenantQueryError):
            list(Widget.objects.all())

    @pytest.mark.parametrize(
        "op",
        [
            lambda qs: qs.count(),
            lambda qs: qs.exists(),
            lambda qs: list(qs.iterator()),
            lambda qs: qs.aggregate(n=Count("id")),
            lambda qs: qs.update(name="x"),
            lambda qs: qs.delete(),
            lambda qs: qs.get(name="a1"),
            lambda qs: qs.first(),
        ],
    )
    def test_every_evaluation_path_raises(self, op: Any) -> None:
        with pytest.raises(UnscopedTenantQueryError):
            op(Widget.objects.filter(name__startswith="a"))

    def test_scoped_query_allowed_and_chain_preserves_scope(self, org: Any) -> None:
        qs = Widget.objects.for_org(org).filter(name__startswith="a").order_by("name")
        assert [w.name for w in qs] == ["a1", "a2"]
        assert qs.exclude(name="a1").count() == 1

    def test_explicit_organisation_filter_counts_as_scoped(self, org: Any) -> None:
        assert Widget.objects.filter(organisation=org).count() == 2
        assert Widget.objects.filter(organisation_id__in=[org.pk]).count() == 2

    def test_negated_org_filter_is_not_scoped(self, org: Any) -> None:
        with pytest.raises(UnscopedTenantQueryError):
            Widget.objects.exclude(organisation=org).count()

    def test_explicit_unscoped_escape_hatch(self) -> None:
        assert Widget.objects.unscoped().count() == 3

    def test_create_is_allowed(self, org: Any) -> None:
        Widget.objects.create(organisation=org, name="new")
        assert Widget.objects.for_org(org).count() == 3


@override_settings(TENANT_STRICT_MODE=False)
@pytest.mark.usefixtures("tenant_guard", "widgets")
def test_guard_disabled_when_not_strict() -> None:
    assert Widget.objects.count() == 3
