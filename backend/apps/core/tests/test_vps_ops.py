"""Production operations on the shared VPS (ADR-033).

EC-OPS-08: disk filling up raises an alert at 80 % (infrastructure/vps/monitor.py), together with
the other host checks (memory, backup age, off-server copy age).
EC-OPS-10: a traffic spike on a viral job post is absorbed by the cached public job board
(apps/jobs/tests/test_public_cache.py) and by nginx rate limits on sign-in and the public jobs API.
"""

from __future__ import annotations

import importlib.util
import os
import re
import time
from collections import namedtuple
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
VPS = ROOT / "infrastructure" / "vps"
Usage = namedtuple("Usage", "total used free")


def _monitor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("mhrs_monitor", VPS / "monitor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "backups").mkdir()
    (tmp_path / "run").mkdir()
    monkeypatch.setattr(module, "APP_DIR", tmp_path)
    monkeypatch.setattr(module, "BACKUPS", tmp_path / "backups")
    return module


def _fresh_backup(module: ModuleType, age_hours: float = 1) -> None:
    dump = module.BACKUPS / "mhrs-db-20261121-014500.dump"
    dump.write_bytes(b"x")
    stamp = time.time() - age_hours * 3600
    os.utime(dump, (stamp, stamp))


def _healthy_memory(monkeypatch: pytest.MonkeyPatch, module: ModuleType, mb: int = 2000) -> None:
    real_read_text = Path.read_text

    def read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.as_posix() == "/proc/meminfo":
            return f"MemTotal: 6000000 kB\nMemAvailable: {mb * 1024} kB\n"
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(module.Path, "read_text", read_text)


def test_disk_alert_fires_at_80_percent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-OPS-08."""
    module = _monitor(tmp_path, monkeypatch)
    _fresh_backup(module)
    _healthy_memory(monkeypatch, module)
    assert module.LIMITS["disk_percent"] == 80
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _p: Usage(100, 79, 21))
    assert module.host_problems() == []
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _p: Usage(100, 81, 19))
    assert module.host_problems() == ["disk / is 81% full"]


def test_low_memory_and_stale_backups_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _monitor(tmp_path, monkeypatch)
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _p: Usage(100, 50, 50))
    _healthy_memory(monkeypatch, module, mb=100)
    problems = module.host_problems()
    assert "only 100 MB of memory available" in problems
    assert "no database backup found" in problems

    _healthy_memory(monkeypatch, module)
    _fresh_backup(module, age_hours=30)
    assert module.host_problems() == ["last database backup is 30 h old"]


def test_off_server_copy_is_checked_once_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _monitor(tmp_path, monkeypatch)
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _p: Usage(100, 50, 50))
    _healthy_memory(monkeypatch, module)
    _fresh_backup(module)
    assert module.host_problems() == []  # not configured yet: no alert
    stamp = tmp_path / "run" / "offsite-last-success"
    stamp.write_text(str(time.time() - 40 * 3600))
    assert module.host_problems() == ["last off-server backup copy is 40 h old"]
    stamp.write_text(str(time.time()))
    assert module.host_problems() == []


def test_nginx_rate_limits_protect_sign_in_and_the_public_job_api() -> None:
    """EC-OPS-10: rate limits in the production nginx site (the job board cache is tested in
    apps/jobs/tests/test_public_cache.py)."""
    conf = (VPS / "nginx" / "mhrs.conf.template").read_text()
    zones = dict(re.findall(r"limit_req_zone \S+ zone=(\w+):\S+ rate=(\S+);", conf))
    assert zones == {"mhrs_auth": "10r/m", "mhrs_search": "60r/m"}
    for location, zone in (("/api/v1/auth/", "mhrs_auth"), ("/api/v1/jobs/", "mhrs_search")):
        block = conf.split(f"location {location} {{", 1)[1].split("}", 1)[0]
        assert f"limit_req zone={zone}" in block and "limit_req_status 429;" in block
    assert "server_tokens off;" in conf
