"""factory_boy factories for organisations (synthetic data only)."""

from __future__ import annotations

import factory

from apps.organisations.models import Organisation


class OrganisationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organisation

    name = factory.Sequence(lambda n: f"Synthetic Employer {n} (Pvt) Ltd")
    slug = factory.Sequence(lambda n: f"synthetic-employer-{n}")
    status = Organisation.Status.ACTIVE
