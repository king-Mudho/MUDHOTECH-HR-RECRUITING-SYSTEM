"""Daily talent pool sweep: reconfirmation reminders, then expiry."""

from __future__ import annotations

from celery import shared_task

from apps.core.tasks import BaseTask

from . import services


@shared_task(name="apps.talentpool.tasks.talent_pool_daily", base=BaseTask)
def talent_pool_daily() -> dict[str, int]:
    return {
        "reminded": services.send_reconfirmation_reminders(),
        "expired": services.expire_due(),
    }
