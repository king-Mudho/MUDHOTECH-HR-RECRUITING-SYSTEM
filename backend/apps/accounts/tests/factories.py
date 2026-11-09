"""factory_boy factories for accounts (synthetic data only)."""

from __future__ import annotations

from typing import Any

import factory

from apps.accounts.models import User

DEFAULT_PASSWORD = "Str0ng-Passw0rd!"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_active = True

    @factory.post_generation
    def password(self, create: bool, extracted: str | None, **kwargs: Any) -> None:
        self.set_password(extracted or DEFAULT_PASSWORD)
        if create:
            self.save(update_fields=["password"])

    @factory.post_generation
    def verified(self, create: bool, extracted: bool | None, **kwargs: Any) -> None:
        """Verified primary EmailAddress by default (allauth requires it to log in)."""
        if not create or extracted is False:
            return
        from allauth.account.models import EmailAddress

        from apps.core import time

        EmailAddress.objects.update_or_create(
            user=self, email=self.email, defaults={"verified": True, "primary": True}
        )
        self.email_verified_at = time.now()
        self.save(update_fields=["email_verified_at"])
