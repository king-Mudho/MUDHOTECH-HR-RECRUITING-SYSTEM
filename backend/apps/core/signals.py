"""Signal wiring: Celery task context for logs, feature-flag cache invalidation."""

from __future__ import annotations

from typing import Any

from celery.signals import before_task_publish, task_postrun, task_prerun
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .context import get_request_id, request_id_var, task_id_var
from .models import FeatureFlag

_tokens: dict[str, tuple[Any, Any]] = {}


@before_task_publish.connect
def _propagate_request_id(headers: dict[str, Any] | None = None, **_: Any) -> None:
    if headers is not None and "mhrs_request_id" not in headers:
        headers["mhrs_request_id"] = get_request_id() or ""


@task_prerun.connect
def _task_context_start(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    rid = getattr(getattr(task, "request", None), "mhrs_request_id", None) or None
    _tokens[task_id or ""] = (task_id_var.set(task_id), request_id_var.set(rid))


@task_postrun.connect
def _task_context_end(task_id: str | None = None, **_: Any) -> None:
    tokens = _tokens.pop(task_id or "", None)
    if tokens:
        task_id_var.reset(tokens[0])
        request_id_var.reset(tokens[1])


@receiver([post_save, post_delete], sender=FeatureFlag)
def _flag_changed(instance: FeatureFlag, **_: Any) -> None:
    from .flags import invalidate

    invalidate(instance.key)
