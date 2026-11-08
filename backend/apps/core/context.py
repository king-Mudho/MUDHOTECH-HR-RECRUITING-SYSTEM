"""Context variables shared by middleware, logging, Celery signals and the tenant guard."""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)
# True while serving an HTTP request: enables the strict unscoped-tenant-query guard.
tenant_guard_var: ContextVar[bool] = ContextVar("tenant_guard", default=False)


def get_request_id() -> str | None:
    return request_id_var.get()
