"""P11-T01: production images and compose follow the deployment baseline (docs/10 §3).

Static checks on `docker-compose.prod.yml` and the Dockerfiles, so a later edit cannot quietly drop
a healthcheck, a memory limit or the non-root user. Skipped where the repository root is not
available (inside the backend image only `backend/` is copied).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker-compose.prod.yml"
DOCKERFILES = [
    ROOT / "backend" / "Dockerfile",
    ROOT / "backend" / "Dockerfile.worker",
    ROOT / "frontend" / "Dockerfile",
]
APP_SERVICES = {
    "backend",
    "worker-default",
    "worker-documents",
    "worker-ai",
    "beat",
    "frontend",
    "flower",
}
# an exact version: digits.digits.digits somewhere in the tag (e.g. 1.30.7-alpine3.24, 3.12.16-slim)
PINNED = re.compile(r":[^:]*\d+\.\d+\.\d+")

pytestmark = pytest.mark.skipif(not COMPOSE.exists(), reason="repository root not available")


def _services() -> dict[str, Any]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert data["name"] == "mhrs"
    services: dict[str, Any] = data["services"]
    return services


def _mem_bytes(value: str) -> int:
    match = re.fullmatch(r"(\d+)([MG])", str(value))
    assert match, f"memory limit {value!r} must be like 512M or 1G"
    return int(match.group(1)) * (1024**2 if match.group(2) == "M" else 1024**3)


def test_every_service_has_restart_healthcheck_limits_and_bounded_logs() -> None:
    services = _services()
    assert {"nginx", "redis", "clamav", *APP_SERVICES} <= set(services)
    for name, svc in services.items():
        assert svc.get("restart") == "unless-stopped", name
        assert svc.get("healthcheck", {}).get("test"), f"{name} has no healthcheck"
        limits = svc.get("deploy", {}).get("resources", {}).get("limits", {})
        assert limits.get("memory") and limits.get("cpus"), f"{name} has no resource limits"
        assert svc.get("logging", {}).get("options", {}).get("max-size"), f"{name} logs unbounded"


def test_memory_budget_fits_the_pilot_host() -> None:
    # t3.xlarge = 16 GB; keep at least ~4 GB for the OS, agents and page cache (flower is opt-in)
    total = sum(
        _mem_bytes(s["deploy"]["resources"]["limits"]["memory"])
        for s in _services().values()
        if "ops" not in s.get("profiles", [])
    )
    assert total <= 12 * 1024**3, f"memory limits add up to {total / 1024**3:.1f} GB"


def test_application_containers_are_hardened() -> None:
    services = _services()
    for name in APP_SERVICES:
        svc = services[name]
        assert "no-new-privileges:true" in svc.get("security_opt", []), name
        assert svc.get("cap_drop") == ["ALL"], name
        assert "ports" not in svc, f"{name} must only be reachable through nginx"
        assert svc.get("privileged") is not True, name


def test_images_are_pinned_and_release_tagged() -> None:
    for name, svc in _services().items():
        image = svc["image"]
        if name in APP_SERVICES:
            assert "${MHRS_TAG:?" in image, f"{name} must use the release tag, never latest"
        else:
            assert PINNED.search(image), f"{name} image {image!r} is not pinned to an exact version"
        assert not image.endswith(":latest"), name


def test_workers_shut_down_warm_and_backend_serves_static_to_nginx() -> None:
    services = _services()
    for name in ("worker-default", "worker-documents", "worker-ai"):
        assert services[name]["stop_grace_period"] == "120s", name
    assert "static:/app/staticfiles" in services["backend"]["volumes"]
    assert "static:/srv/static:ro" in services["nginx"]["volumes"]
    assert services["frontend"]["environment"]["API_INTERNAL_URL"] == "http://backend:8000"


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_dockerfiles_are_multistage_pinned_and_non_root(dockerfile: Path) -> None:
    text = dockerfile.read_text(encoding="utf-8")
    stages = re.findall(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?", text, flags=re.MULTILINE)
    assert len(stages) >= 2, "expected a multi-stage build"
    for arg in re.findall(r"^ARG\s+\w+_IMAGE=(\S+)", text, flags=re.MULTILINE):
        assert PINNED.search(arg), f"base {arg} is not pinned to an exact version"
    stage_names = {stage for _image, stage in stages if stage}
    for image, _stage in stages:
        assert not image.endswith(":latest"), image
        if not image.startswith("$") and image not in stage_names:
            assert PINNED.search(image), f"{image} is not pinned to an exact version"
    # the last stage is the runtime: it switches to the unprivileged uid and declares the version
    runtime = text[text.rindex("\nFROM ") :]
    assert re.search(r"^USER 10001$", runtime, flags=re.MULTILINE), "runtime must run as uid 10001"
    assert "MHRS_VERSION" in runtime
    assert "uv " not in runtime.split("COPY --from=builder")[-1], "uv must stay in the builder"
