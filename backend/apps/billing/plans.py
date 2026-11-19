"""Default plans (decision D-13: placeholders, editable by platform admins).

Seeded on ``post_migrate`` (transactional tests flush the database): a plan is created only when
its code is missing, so edits made in the admin are never overwritten.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import Plan

DEFAULT_PLANS: list[dict[str, Any]] = [
    {
        "code": "trial",
        "name": "Free trial",
        "description": "30 days to try the full workflow.",
        "limits": {"active_vacancies": 2, "seats": 3, "ai_evaluations_month": 200, "storage_gb": 2},
        "price_usd": Decimal("0"),
        "price_zwg": Decimal("0"),
        "is_trial": True,
        "is_public": False,
        "order": 0,
    },
    {
        "code": "starter",
        "name": "Starter",
        "description": "For small teams hiring a few roles at a time.",
        "limits": {
            "active_vacancies": 5,
            "seats": 5,
            "ai_evaluations_month": 1000,
            "storage_gb": 10,
        },
        "price_usd": Decimal("49.00"),
        "price_zwg": None,
        "order": 1,
    },
    {
        "code": "growth",
        "name": "Growth",
        "description": "For growing organisations with regular recruitment.",
        "limits": {
            "active_vacancies": 25,
            "seats": 20,
            "ai_evaluations_month": 5000,
            "storage_gb": 50,
        },
        "price_usd": Decimal("149.00"),
        "price_zwg": None,
        "order": 2,
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Custom limits and pricing - contact MudhoTech Solutions.",
        "limits": {},
        "price_usd": None,
        "price_zwg": None,
        "order": 3,
    },
]


def seed_default_plans() -> int:
    created = 0
    for spec in DEFAULT_PLANS:
        _, was_created = Plan.objects.get_or_create(code=spec["code"], defaults=dict(spec))
        created += int(was_created)
    return created
