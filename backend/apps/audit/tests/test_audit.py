from __future__ import annotations

import threading
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import RequestFactory

from apps.accounts.tests.factories import UserFactory
from apps.audit import services as audit
from apps.audit.models import PLATFORM_CHAIN, AccessLog, ActorType, AuditEvent
from apps.core.context import request_id_var

pytestmark = pytest.mark.django_db


def test_record_builds_per_org_chain(org: Any, other_org: Any) -> None:
    actor = UserFactory()
    e1 = audit.record(
        actor=actor, action="org.updated", target=org, before={"a": 1}, after={"a": 2}
    )
    e2 = audit.record(actor=actor, action="org.updated", target=org)
    e3 = audit.record(actor=actor, action="org.updated", target=other_org)
    platform = audit.record(action="platform.boot")
    assert (e1.chain, e1.seq, e1.prev_hash) == (str(org.pk), 1, audit.GENESIS)
    assert (e2.seq, e2.prev_hash) == (2, e1.hash)
    assert e3.chain == str(other_org.pk) and e3.seq == 1
    assert platform.chain == PLATFORM_CHAIN and platform.actor_type == ActorType.SYSTEM
    assert e1.organisation_id == org.pk and e1.actor_type == ActorType.HUMAN
    assert list(audit.verify_chain(str(org.pk))) == []


def test_request_metadata_is_minimised(org: Any) -> None:
    req = RequestFactory().post("/x", REMOTE_ADDR="196.43.10.77", HTTP_USER_AGENT="Mozilla/5.0")
    token = request_id_var.set("req_AUDIT0001")
    try:
        event = audit.record(
            actor=None,
            action="invitation.created",
            target=("organisations.invitation", "abc"),
            organisation=org,
            after={"email": "x@example.test", "token_hash": "deadbeef"},
            request=req,
            reason="new hire",
        )
    finally:
        request_id_var.reset(token)
    assert event.ip_trunc == "196.43.10.0/24"
    assert len(event.user_agent_hash) == 32 and "Mozilla" not in event.user_agent_hash
    assert event.after == {"email": "x@example.test", "token_hash": "[redacted]"}
    assert event.request_id == "req_AUDIT0001"
    assert event.target_type == "organisations.invitation"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2001:db8:abcd:12::1", "2001:db8:abcd::/48"),
        ("garbage", ""),
        (None, ""),
        ("10.1.2.3, 172.16.0.1", "10.1.2.0/24"),
    ],
)
def test_truncate_ip(raw: str | None, expected: str) -> None:
    assert audit.truncate_ip(raw) == expected


def test_anonymous_actor_is_recorded_as_system() -> None:
    from django.contrib.auth.models import AnonymousUser

    event = audit.record(actor=AnonymousUser(), action="x.y")
    assert event.actor_id is None and event.actor_type == ActorType.SYSTEM


def test_update_and_delete_are_rejected_by_database(org: Any) -> None:
    event = audit.record(action="org.created", target=org)
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()
    log = audit.log_access(user=None, target=org, organisation=org)
    with pytest.raises(DatabaseError), transaction.atomic():
        AccessLog.objects.filter(pk=log.pk).update(action="x")


def test_tampering_is_detected_by_verification(org: Any) -> None:
    for i in range(3):
        audit.record(action="org.updated", target=org, after={"i": i})
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET LOCAL mhrs.audit_maintenance = 'on'")
        AuditEvent.objects.filter(chain=str(org.pk), seq=2).update(reason="edited later")
    breaks = list(audit.verify_chain(str(org.pk)))
    assert [(b.seq, b.reason) for b in breaks] == [(2, "hash mismatch (event content altered)")]
    with pytest.raises(CommandError):
        call_command("verify_audit_chain", stdout=StringIO(), stderr=StringIO())


def test_deleted_event_breaks_chain(org: Any) -> None:
    for _ in range(3):
        audit.record(action="org.updated", target=org)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET LOCAL mhrs.audit_maintenance = 'on'")
        AuditEvent.objects.filter(chain=str(org.pk), seq=2).delete()
    reasons = {b.reason for b in audit.verify_chain(str(org.pk))}
    assert "sequence gap (expected 2)" in reasons
    assert "prev_hash does not match previous event" in reasons


def test_verify_command_ok(org: Any) -> None:
    audit.record(action="org.created", target=org)
    out = StringIO()
    call_command("verify_audit_chain", stdout=out)
    assert "OK - 1 chain(s)" in out.getvalue()
    call_command("verify_audit_chain", "--chain", str(org.pk), stdout=out)


def test_rolled_back_business_transaction_drops_event(org: Any) -> None:
    with pytest.raises(RuntimeError), transaction.atomic():
        audit.record(action="org.updated", target=org)
        raise RuntimeError("business failure")
    assert not AuditEvent.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_writers_do_not_fork_chain(org: Any) -> None:
    barrier = threading.Barrier(4)

    def write() -> None:
        try:
            barrier.wait()
            for _ in range(5):
                audit.record(action="concurrent", target=org)
        finally:
            connection.close()

    threads = [threading.Thread(target=write) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = list(AuditEvent.objects.filter(chain=str(org.pk)).values_list("seq", flat=True))
    assert sorted(seqs) == list(range(1, 21))
    assert list(audit.verify_chain(str(org.pk))) == []


def test_log_access_with_tuple_target(org: Any) -> None:
    user = UserFactory()
    log = audit.log_access(
        user=user, target=("documents.document", "d1"), organisation=org, action="download"
    )
    assert (log.target_type, log.target_id, log.action) == ("documents.document", "d1", "download")
    assert str(log).startswith("download")
