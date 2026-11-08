"""Logging helpers: inject request/task ids into every record for structured JSON logs."""

from __future__ import annotations

import logging

from .context import request_id_var, task_id_var


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.task_id = task_id_var.get()
        return True
