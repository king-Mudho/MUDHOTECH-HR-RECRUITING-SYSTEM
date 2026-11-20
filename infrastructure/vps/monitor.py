"""MHRS production monitor for the shared VPS (ADR-033): runs every 5 minutes (mhrs-monitor.timer).

Checks the live site, the MHRS services, disk, memory, the processing backlog, failed tasks,
virus signatures, backups and the TLS certificate. Emails OPS_ALERT_EMAILS (backend .env) when a
problem appears, a reminder every 6 hours while it lasts, and once when everything has recovered.

Run by monitor.sh as the mhrs user with the backend environment loaded:
    python infrastructure/vps/monitor.py [--test]
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

APP_DIR = Path("/srv/mhrs")
STATE = APP_DIR / "run" / "monitor-state.json"
BACKUPS = APP_DIR / "backups"
REMIND_SECONDS = 6 * 3600

# thresholds, the same as docs/10 section 8
LIMITS = {
    "documents_queue": 500,
    "backlog_seconds": 15 * 60,
    "outbox_lag_seconds": 5 * 60,
    "dead_letters": 10,
    "email_failure_percent": 5.0,
    "clamav_age_hours": 48,
    "disk_percent": 85,
    "memory_available_mb": 250,
    "backup_age_hours": 26,
    "cert_days": 14,
}


def site_problems(domain: str) -> list[str]:
    problems = []
    for path in ("/readyz", "/"):
        try:
            with urllib.request.urlopen(f"https://{domain}{path}", timeout=20) as r:  # nosec B310
                if r.status != 200:
                    problems.append(f"https://{domain}{path} answered {r.status}")
        except Exception as exc:  # noqa: BLE001 - any failure is the signal
            problems.append(
                f"https://{domain}{path} failed: {type(exc).__name__}: {exc}"[:200]
            )
    return problems


def cert_days_left(domain: str) -> float:
    ctx = ssl.create_default_context()
    with (
        socket.create_connection((domain, 443), timeout=15) as sock,
        ctx.wrap_socket(sock, server_hostname=domain) as tls,
    ):
        expires = ssl.cert_time_to_seconds(tls.getpeercert()["notAfter"])
    return (expires - time.time()) / 86400


def host_problems() -> list[str]:
    problems = []
    usage = shutil.disk_usage("/")
    percent = usage.used / usage.total * 100
    if percent > LIMITS["disk_percent"]:
        problems.append(f"disk / is {percent:.0f}% full")
    meminfo = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    available_mb = int(meminfo["MemAvailable"].split()[0]) / 1024
    if available_mb < LIMITS["memory_available_mb"]:
        problems.append(f"only {available_mb:.0f} MB of memory available")
    dumps = sorted(BACKUPS.glob("mhrs-db-*.dump"), key=lambda p: p.stat().st_mtime)
    if not dumps:
        problems.append("no database backup found")
    else:
        age_h = (time.time() - dumps[-1].stat().st_mtime) / 3600
        if age_h > LIMITS["backup_age_hours"]:
            problems.append(f"last database backup is {age_h:.0f} h old")
    return problems


def app_problems() -> list[str]:
    import django

    django.setup()
    from apps.core.ops_metrics import collect

    metrics, errors = collect()
    values = {
        name + ("" if not dims else f"[{','.join(dims.values())}]"): value
        for name, value, _unit, dims in metrics
    }
    problems = [
        f"metric source '{name}' failing ({err})" for name, err in errors.items()
    ]
    checks = [
        (
            "QueueDepth[documents]",
            "documents_queue",
            "documents waiting to be processed",
        ),
        (
            "ProcessingBacklogAgeSeconds",
            "backlog_seconds",
            "seconds the oldest application has waited",
        ),
        ("OutboxLagSeconds", "outbox_lag_seconds", "seconds the event relay is behind"),
        (
            "DeadLettersOpen",
            "dead_letters",
            "tasks that failed permanently (dead letters)",
        ),
        (
            "EmailFailureRatePercent",
            "email_failure_percent",
            "% of emails failing in the last hour",
        ),
        (
            "ClamavSignatureAgeHours",
            "clamav_age_hours",
            "hours since the virus signatures were updated",
        ),
    ]
    for key, limit, label in checks:
        if key in values and values[key] > LIMITS[limit]:
            problems.append(f"{values[key]:.0f} {label} (limit {LIMITS[limit]})")
    return problems


def send(subject: str, body: str) -> None:
    from django.conf import settings
    from django.core.mail import send_mail

    recipients = [
        a.strip()
        for a in os.environ.get("OPS_ALERT_EMAILS", "").split(",")
        if a.strip()
    ]
    if not recipients:
        print("OPS_ALERT_EMAILS is not set; not emailing", file=sys.stderr)
        return
    send_mail(
        subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False
    )


def main() -> int:
    domain = os.environ.get("SITE_DOMAIN", "hr.agribizframework.com")
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if "--test" in sys.argv:
        import django

        django.setup()
        send(
            f"[MHRS] Test alert from {domain}",
            f"This is a test of the MHRS production alerts ({now}). No action is needed.\n",
        )
        print("test alert sent")
        return 0

    problems = site_problems(domain) + host_problems()
    problems += [
        f"service {s} is {state}"
        for s, state in (
            item.split("=", 1)
            for item in os.environ.get("SERVICE_STATES", "").split()
            if "=" in item
        )
        if state != "active"
    ]
    try:
        days = cert_days_left(domain)
        if days < LIMITS["cert_days"]:
            problems.append(f"TLS certificate expires in {days:.0f} days")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"TLS check failed: {type(exc).__name__}")
    try:
        problems += app_problems()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"application checks failed: {type(exc).__name__}: {exc}"[:200])

    state = (
        json.loads(STATE.read_text()) if STATE.exists() else {"problems": [], "sent": 0}
    )
    previous, last_sent = set(state["problems"]), state.get("sent", 0)
    current = set(problems)
    subject = body = ""
    if current and (current != previous or time.time() - last_sent > REMIND_SECONDS):
        subject = f"[MHRS] {len(current)} problem(s) on {domain}"
        body = (
            f"Checked {now}.\n\n"
            + "\n".join(f"- {p}" for p in sorted(current))
            + "\n\nRunbooks: /srv/mhrs/docs/runbooks/ and infrastructure/vps/README.md"
            + "\nLogs: journalctl -u mhrs-backend -u mhrs-worker -u mhrs-frontend -n 100\n"
        )
    elif previous and not current:
        subject = f"[MHRS] Recovered: {domain} is healthy again"
        body = f"Checked {now}. All MHRS checks pass again.\n\nResolved:\n" + "\n".join(
            f"- {p}" for p in sorted(previous)
        )
    for p in sorted(current):
        print(f"PROBLEM {p}")
    if subject:
        try:
            send(subject, body)
            last_sent = time.time()
        except Exception as exc:  # noqa: BLE001 - mail failure must not hide the problems
            print(f"ALERT EMAIL FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
    STATE.write_text(json.dumps({"problems": sorted(current), "sent": last_sent}))
    if not current:
        print("all checks pass")
    return 1 if current else 0


if __name__ == "__main__":
    raise SystemExit(main())
