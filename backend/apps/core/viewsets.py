"""Base DRF viewsets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet
from rest_framework import viewsets

from .exceptions import PermissionDeniedError
from .models import TenantModel

if TYPE_CHECKING:
    from apps.organisations.models import Organisation


class TenantScopedViewSet(viewsets.ModelViewSet):
    """ModelViewSet that is always scoped to ``request.organisation``.

    * ``request.organisation`` is resolved server-side (OrganisationContextMiddleware, Phase 2)
      from a validated membership - never from the request body.
    * Objects belonging to another organisation are simply not in the queryset, so detail/mutation
      requests return 404 ``not_found`` (no existence leak across tenants).
    * ``perform_create`` stamps the organisation; serializers must not expose ``organisation`` as
      writable.
    """

    def get_organisation(self) -> Organisation:
        org = getattr(self.request, "organisation", None)
        if org is None:
            raise PermissionDeniedError(
                code="permission_denied",
                message="An organisation context is required for this endpoint.",
                details={"reason": "org_context_required"},
            )
        return org

    def get_queryset(self) -> QuerySet[Any]:
        model = self.queryset.model if self.queryset is not None else None
        if model is None or not issubclass(model, TenantModel):
            raise TypeError("TenantScopedViewSet requires a queryset of a TenantModel subclass.")
        base: Any = self.queryset.all()  # type: ignore[union-attr]
        return base.for_org(self.get_organisation())

    def perform_create(self, serializer: Any) -> None:
        serializer.save(organisation=self.get_organisation())
