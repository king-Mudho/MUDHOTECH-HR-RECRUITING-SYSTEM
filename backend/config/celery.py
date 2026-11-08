"""Celery application for MHRS.

Queues: default, documents, ai, notifications, reports (docs/02 §2).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("mhrs")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
