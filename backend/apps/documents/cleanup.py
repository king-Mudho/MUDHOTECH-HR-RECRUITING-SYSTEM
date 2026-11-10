"""Housekeeping for uploads (P04-T04, EC-APP-08).

* Pending upload sessions past ``expires_at`` become ``expired``; their object (if the browser did
  upload but never confirmed) is deleted once older than the grace period.
* Rejected/infected files are purged from quarantine after the grace period; the ``Document`` row
  stays (audit trail, candidate-facing status) with ``deleted_at`` set.
* Any other quarantine object older than the grace period that no live session or pending
  document references is deleted (crashed uploads, manual leftovers).
Everything is idempotent and safe to run concurrently with uploads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from apps.core import storage
from apps.core.time import now

from .models import Document, ScanStatus, UploadSession

logger = logging.getLogger(__name__)
GRACE = timedelta(hours=24)


@dataclass
class CleanupResult:
    sessions_expired: int = 0
    rejected_purged: int = 0
    orphans_deleted: int = 0


def _delete_quietly(key: str) -> bool:
    try:
        storage.delete_object("quarantine", key)
        return True
    except Exception:
        logger.warning("quarantine_delete_failed", extra={"key": key})
        return False


def run(batch: int = 500) -> CleanupResult:
    result = CleanupResult()
    current = now()

    # 1. expire sessions the browser never completed
    stale = UploadSession.objects.filter(
        status=UploadSession.Status.PENDING, expires_at__lt=current
    )
    result.sessions_expired = stale.update(status=UploadSession.Status.EXPIRED, updated_at=current)

    # 2. purge rejected/infected content from quarantine after the grace period
    rejected = Document.objects.filter(
        bucket="quarantine",
        deleted_at__isnull=True,
        scan_status__in=[ScanStatus.INFECTED, ScanStatus.REJECTED],
        created_at__lt=current - GRACE,
    )[:batch]
    for doc in rejected:
        if _delete_quietly(doc.storage_key):
            Document.objects.filter(pk=doc.pk).update(deleted_at=current, updated_at=current)
            result.rejected_purged += 1

    # 3. orphan objects: old, and not referenced by a live session or a pending document
    cutoff = current - GRACE
    live_keys = set(
        UploadSession.objects.filter(status=UploadSession.Status.PENDING).values_list(
            "object_key", flat=True
        )
    ) | set(
        Document.objects.filter(bucket="quarantine", scan_status=ScanStatus.PENDING).values_list(
            "storage_key", flat=True
        )
    )
    paginator = storage.client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=storage.bucket_for("quarantine")):
        for obj in page.get("Contents", []):
            if obj["LastModified"] >= cutoff or obj["Key"] in live_keys:
                continue
            if _delete_quietly(obj["Key"]):
                result.orphans_deleted += 1
            if result.orphans_deleted >= batch:
                return result
    return result
