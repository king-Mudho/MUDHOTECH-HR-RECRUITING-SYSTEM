"""Celery base task + core periodic tasks."""

from __future__ import annotations

import logging
import traceback as tb
from typing import Any

from celery import Task, shared_task
from django.core.serializers.json import DjangoJSONEncoder

from . import time
from .context import get_request_id

logger = logging.getLogger("mhrs.tasks")


def _json_safe(value: Any) -> Any:
    import json

    try:
        return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
    except (TypeError, ValueError):
        return repr(value)


class BaseTask(Task):
    """Base class for every MHRS task.

    * ``acks_late`` + ``reject_on_worker_lost``: a crashed worker does not lose the task.
    * Bounded retries with exponential backoff and jitter (30 s base, max 10 min, 3 retries).
    * On final failure a :class:`~apps.core.models.DeadLetter` row is written for the HR/ops queue.
    * Tasks must be idempotent; idempotency key convention ``<event>:<object_id>:<version>``.
    """

    acks_late = True
    reject_on_worker_lost = True
    autoretry_for = (Exception,)
    dont_autoretry_for: tuple[type[BaseException], ...] = ()
    max_retries = 3
    retry_backoff = 30
    retry_backoff_max = 600
    retry_jitter = True

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        from .models import DeadLetter

        try:
            DeadLetter.objects.create(
                task_name=self.name,
                task_id=task_id or "",
                args=_json_safe(list(args or [])),
                kwargs=_json_safe(dict(kwargs or {})),
                error=f"{type(exc).__name__}: {exc}"[:4000],
                traceback="".join(tb.format_exception(exc))[:20000],
                organisation_id=(kwargs or {}).get("organisation_id"),
                request_id=get_request_id() or "",
            )
        except Exception:  # pragma: no cover - never mask the original failure
            logger.exception("dead_letter_write_failed")
        logger.error("task_failed_final", extra={"task_name": self.name, "task_id": task_id})
        super().on_failure(exc, task_id, args, kwargs, einfo)  # type: ignore[arg-type]


@shared_task(name="apps.core.tasks.ping", base=BaseTask)
def ping() -> str:
    """Smoke-test task: proves a worker consumes the default queue."""
    logger.info("ping")
    return "pong"


@shared_task(name="apps.core.tasks.relay_outbox", base=BaseTask, max_retries=0)
def relay_outbox() -> dict[str, int]:
    from .outbox import relay_batch

    result = relay_batch()
    return {"published": result.published, "failed": result.failed}


@shared_task(name="apps.core.tasks.purge_expired_idempotency_keys", base=BaseTask)
def purge_expired_idempotency_keys() -> int:
    from .models import IdempotencyKey

    deleted, _ = IdempotencyKey.objects.filter(expires_at__lt=time.now()).delete()
    return deleted
