"""Talent pool consent lifecycle (P13-T01).

* ``join`` - the candidate opts in to **one** employer's pool (at the end of an application or
  from their privacy page). Only employers they have applied to can be joined, so an employer never
  sees someone who has not dealt with it. Every opt-in writes a ``talent_pool`` consent record with
  the employer's current privacy-notice version; joining again while a member is a reconfirmation
  and restarts the period (default 12 months).
* ``leave`` - withdraws the consent at once; the entry stops being searchable. ``delete=True``
  also removes the entry and the employer's tags (the consent records stay as proof).
* ``send_reconfirmation_reminders`` / ``expire_due`` - daily: a reminder 30 days before the end,
  then the entry lapses (it is never extended without the candidate acting).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet

from apps.applications.models import Application, Status
from apps.audit import services as audit
from apps.core.exceptions import NotFoundError
from apps.core.time import now
from apps.privacy import services as privacy
from apps.privacy.models import ConsentRecord, Purpose

from .models import EntryStatus, TalentPoolEntry

REMIND_BEFORE = timedelta(days=30)


def period() -> timedelta:
    months = int(getattr(settings, "TALENT_POOL_MONTHS", 12))
    return timedelta(days=round(months * 365 / 12))


def applied_organisations(user: Any) -> QuerySet[Application]:
    """Employers the person has submitted an application to (system read across employers,
    restricted to the person's own applications)."""
    return (
        Application.objects.unscoped()
        .filter(candidate_user=user)
        .exclude(status__in=[Status.DRAFT, Status.ABANDONED])
        .exclude(submitted_at__isnull=True)
    )


def searchable(organisation_id: Any) -> QuerySet[TalentPoolEntry]:
    """Entries an employer may search: active, unexpired, consent not withdrawn."""
    return TalentPoolEntry.objects.for_org(organisation_id).filter(
        status=EntryStatus.ACTIVE,
        expires_at__gt=now(),
        consent_record__withdrawn_at__isnull=True,
        consent_record__granted=True,
    )


def join(
    user: Any,
    organisation_id: Any,
    *,
    ip: str | None = None,
    source_application: Application | None = None,
) -> TalentPoolEntry:
    apps = applied_organisations(user).filter(organisation_id=organisation_id)
    if not apps.exists():
        # same answer as an unknown employer: nothing reveals other organisations' existence
        raise NotFoundError()
    moment = now()
    with transaction.atomic():
        version, _ = privacy.privacy_notice_version(organisation_id)
        source = source_application or apps.order_by("-submitted_at").first()
        consent = privacy.record(
            user,
            Purpose.TALENT_POOL,
            granted=True,
            notice_version=version,
            organisation=organisation_id,
            ip=ip,
            context={"application_id": str(source.pk) if source else None},
        )
        entry = (
            TalentPoolEntry.objects.for_org(organisation_id)
            .select_for_update()
            .filter(candidate_user=user)
            .select_related("consent_record")
            .first()
        )
        reconfirm = (
            entry is not None
            and entry.status == EntryStatus.ACTIVE
            and entry.consent_record.withdrawn_at is None
        )
        if entry is None:
            entry = TalentPoolEntry(
                organisation_id=organisation_id,
                candidate_user=user,
                joined_at=moment,
                source_application=source,
            )
        elif not reconfirm:  # coming back after leaving or lapsing: a fresh membership
            entry.joined_at = moment
            entry.left_at = None
        entry.consent_record = consent
        entry.status = EntryStatus.ACTIVE
        entry.expires_at = moment + period()
        entry.reconfirmed_at = moment if reconfirm else None
        entry.reminder_sent_at = None
        entry.save()
        audit.record(
            actor=user,
            actor_type="candidate",
            action="talent_pool.reconfirmed" if reconfirm else "talent_pool.joined",
            target=entry,
            organisation=organisation_id,
            after={"expires_at": entry.expires_at.isoformat()},
        )
    return entry


def _withdraw_consents(user: Any, organisation_id: Any, at: Any) -> int:
    return ConsentRecord.objects.filter(
        user=user,
        organisation_id=organisation_id,
        purpose=Purpose.TALENT_POOL,
        withdrawn_at__isnull=True,
    ).update(withdrawn_at=at)


def leave(user: Any, organisation_id: Any, *, delete: bool = False) -> TalentPoolEntry | None:
    moment = now()
    with transaction.atomic():
        entry = (
            TalentPoolEntry.objects.for_org(organisation_id)
            .select_for_update()
            .filter(candidate_user=user)
            .first()
        )
        if entry is None:
            raise NotFoundError()
        _withdraw_consents(user, organisation_id, moment)
        audit.record(
            actor=user,
            actor_type="candidate",
            action="talent_pool.deleted" if delete else "talent_pool.left",
            target=entry,
            organisation=organisation_id,
        )
        if delete:
            entry.delete()
            return None
        entry.status = EntryStatus.WITHDRAWN
        entry.left_at = moment
        entry.save(update_fields=["status", "left_at", "updated_at"])
    return entry


def erase_for(user: Any, organisation_id: Any = None) -> int:
    """Erasure (docs/06): remove the person's pool entries (all employers or one)."""
    rows = TalentPoolEntry.objects.unscoped().filter(candidate_user=user)
    if organisation_id is not None:
        rows = rows.filter(organisation_id=organisation_id)
    moment = now()
    for org_id in set(rows.values_list("organisation_id", flat=True)):
        _withdraw_consents(user, org_id, moment)
    return int(rows.delete()[0])


def status_for(user: Any) -> list[dict[str, Any]]:
    """One row per employer the person applied to, with their pool membership (if any)."""
    orgs: dict[Any, str] = {}
    for org_id, name in (
        applied_organisations(user)
        .order_by("organisation__name")
        .values_list("organisation_id", "organisation__name")
    ):
        orgs.setdefault(org_id, name)
    entries = {
        e.organisation_id: e
        for e in TalentPoolEntry.objects.unscoped()
        .filter(candidate_user=user, organisation_id__in=list(orgs))
        .select_related("consent_record")
    }
    moment = now()
    rows = []
    for org_id, name in orgs.items():
        e = entries.get(org_id)
        state = "none"
        if e is not None:
            state = e.status
            if e.status == EntryStatus.ACTIVE and e.consent_record.withdrawn_at is not None:
                state = EntryStatus.WITHDRAWN  # withdrawn from the general consents list
            elif e.status == EntryStatus.ACTIVE and e.expires_at <= moment:
                state = EntryStatus.EXPIRED
        rows.append(
            {
                "organisation_id": org_id,
                "organisation_name": name,
                "status": str(state),
                "joined_at": e.joined_at if e else None,
                "expires_at": e.expires_at if e else None,
                "reconfirm_due": bool(
                    e
                    and e.status == EntryStatus.ACTIVE
                    and moment < e.expires_at <= moment + REMIND_BEFORE
                ),
            }
        )
    return rows


def entry_row(user: Any, organisation_id: Any) -> dict[str, Any]:
    for row in status_for(user):
        if str(row["organisation_id"]) == str(organisation_id):
            return row
    raise NotFoundError()


# --- scheduled ------------------------------------------------------------------------------------
def send_reconfirmation_reminders() -> int:
    from apps.notifications import delivery as notifications

    moment = now()
    due = (
        TalentPoolEntry.objects.unscoped()  # system sweep across employers
        .filter(
            status=EntryStatus.ACTIVE,
            reminder_sent_at__isnull=True,
            expires_at__gt=moment,
            expires_at__lte=moment + REMIND_BEFORE,
        )
        .select_related("organisation", "candidate_user")
    )
    sent = 0
    for entry in due:
        with transaction.atomic():
            notifications.notify(
                entry.candidate_user,
                "talent_pool_reconfirm",
                {
                    "organisation_name": entry.organisation.name,
                    "expires_on": f"{entry.expires_at.day} {entry.expires_at:%B %Y}",
                    "privacy_url": f"{settings.FRONTEND_URL}/candidate/privacy#talent-pool",
                },
                dedupe_key=f"talent_pool_reconfirm:{entry.pk}:{entry.expires_at.date()}",
                organisation=entry.organisation,
            )
            TalentPoolEntry.objects.unscoped().filter(pk=entry.pk).update(reminder_sent_at=moment)
        sent += 1
    return sent


def expire_due() -> int:
    moment = now()
    due = TalentPoolEntry.objects.unscoped().filter(
        status=EntryStatus.ACTIVE, expires_at__lte=moment
    )
    count = 0
    for entry in due:
        with transaction.atomic():
            TalentPoolEntry.objects.unscoped().filter(
                pk=entry.pk, status=EntryStatus.ACTIVE
            ).update(status=EntryStatus.EXPIRED, updated_at=moment)
            audit.record(
                actor=None,
                actor_type="system",
                action="talent_pool.expired",
                target=entry,
                organisation=entry.organisation_id,
            )
        count += 1
    return count
