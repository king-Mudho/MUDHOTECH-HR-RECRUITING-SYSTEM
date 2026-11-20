"""Public API v1 with scoped API keys and job feeds (P15-T06, docs/03 api_keys).

* Keys look like ``mhrs_<prefix>_<secret>``; only a SHA-256 hash is stored and the full key is
  shown once. Scopes: ``jobs:read`` (the organisation's vacancies) and ``applications:read``
  (application references, statuses and dates only - no names, contacts, documents or AI output).
* Requests authenticate with ``Authorization: Bearer <key>`` and are rate limited per key.
* Feeds: ``/api/v1/feeds/<org-slug>/jobs.xml`` (Indeed-style XML) and ``jobs.json`` list the
  organisation's public, open vacancies (cached briefly, no authentication).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any
from xml.sax.saxutils import escape  # nosec B406 - escapes text we write; no XML is parsed

from django.conf import settings
from django.db import transaction
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle

from apps.audit import services as audit
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.time import now

from .models import ApiKey

SCOPES = ("jobs:read", "applications:read")


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def create_key(membership: Any, *, name: str, scopes: list[str]) -> tuple[ApiKey, str]:
    unknown = set(scopes) - set(SCOPES)
    if not scopes or unknown:
        raise DomainError(
            "validation_error",
            "Choose at least one supported scope.",
            details={"scopes": [f"Supported: {', '.join(SCOPES)}"]},
        )
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    with transaction.atomic():
        key = ApiKey.objects.create(
            organisation_id=membership.organisation_id,
            name=name.strip()[:80] or "API key",
            prefix=prefix,
            key_hash=_hash(secret),
            scopes=sorted(set(scopes)),
            created_by=membership.user,
        )
        audit.record(
            actor=membership.user,
            action="api_keys.created",
            target=key,
            organisation=membership.organisation_id,
            after={"name": key.name, "scopes": key.scopes, "prefix": prefix},
        )
    return key, f"mhrs_{prefix}_{secret}"


def revoke_key(membership: Any, key_id: Any) -> ApiKey:
    key = ApiKey.objects.for_org(membership.organisation_id).filter(pk=key_id).first()
    if key is None:
        raise NotFoundError()
    if key.revoked_at is None:
        key.revoked_at = now()
        key.save(update_fields=["revoked_at", "updated_at"])
        audit.record(
            actor=membership.user,
            action="api_keys.revoked",
            target=key,
            organisation=membership.organisation_id,
        )
    return key


class ApiKeyPrincipal:
    """Stands in for a user on API-key requests (``request.user``)."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, key: ApiKey) -> None:
        self.key = key
        self.pk = None
        self.organisation_id = key.organisation_id


class ApiKeyAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[ApiKeyPrincipal, ApiKey] | None:
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(f"{self.keyword} mhrs_"):
            return None
        token = header[len(self.keyword) + 1 :].strip()
        try:
            _, prefix, secret = token.split("_", 2)
        except ValueError as exc:
            raise AuthenticationFailed("Invalid API key.") from exc
        key = ApiKey.objects.unscoped().filter(prefix=prefix, revoked_at__isnull=True).first()
        if key is None or not hmac.compare_digest(key.key_hash, _hash(secret)):
            raise AuthenticationFailed("Invalid API key.")
        ApiKey.objects.unscoped().filter(pk=key.pk).update(last_used_at=now())
        return ApiKeyPrincipal(key), key

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


def HasScope(scope: str) -> type[BasePermission]:  # noqa: N802 (permission factory)
    class _Scope(BasePermission):
        def has_permission(self, request: Request, view: Any) -> bool:
            key = request.auth
            return isinstance(key, ApiKey) and scope in (key.scopes or [])

    _Scope.__name__ = f"HasScope_{scope.replace(':', '_')}"
    return _Scope


class ApiKeyThrottle(SimpleRateThrottle):
    scope = "api_key"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        key = request.auth
        if not isinstance(key, ApiKey):
            return None
        return f"throttle_api_key_{key.pk}"


# --- feeds --------------------------------------------------------------------------------------
def feed_jobs(org_slug: str) -> list[dict[str, Any]]:
    from apps.jobs.selectors import public_jobs

    jobs = public_jobs({"org": org_slug}).select_related("organisation", "published_version")
    out = []
    for job in jobs[:500]:
        version = job.published_version
        locations = list(job.locations.all())
        out.append(
            {
                "id": str(job.pk),
                "title": job.title,
                "company": job.organisation.name,
                "url": f"{settings.FRONTEND_URL}/jobs/{job.slug}",
                "apply_url": f"{settings.FRONTEND_URL}/apply/{job.pk}",
                "city": locations[0].city if locations else "",
                "country": "ZW",
                "employment_type": job.employment_type,
                "published_at": job.published_at.isoformat() if job.published_at else None,
                "closes_at": job.closes_at.isoformat() if job.closes_at else None,
                "summary": getattr(version, "summary", "") or "",
            }
        )
    return out


def _cdata(text: str) -> str:
    return "<![CDATA[" + str(text).replace("]]>", "]]]]><![CDATA[>") + "]]>"


def jobs_xml(org_slug: str) -> str:
    rows = feed_jobs(org_slug)
    items = []
    for j in rows:
        items.append(
            "<job>"
            f"<title>{_cdata(j['title'])}</title>"
            f"<date>{escape(j['published_at'] or '')}</date>"
            f"<referencenumber>{escape(j['id'])}</referencenumber>"
            f"<url>{escape(j['url'])}</url>"
            f"<company>{_cdata(j['company'])}</company>"
            f"<city>{escape(j['city'])}</city>"
            f"<country>{escape(j['country'])}</country>"
            f"<jobtype>{escape(j['employment_type'] or '')}</jobtype>"
            f"<expirationdate>{escape(j['closes_at'] or '')}</expirationdate>"
            f"<description>{_cdata(j['summary'])}</description>"
            "</job>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f"<source><publisher>MUDHOTECH HR RECRUITING SYSTEM</publisher>"
        f"<publisherurl>{escape(settings.FRONTEND_URL)}</publisherurl>"
        f"{''.join(items)}</source>"
    )


# OpenAPI: document the bearer API key scheme for the public API endpoints
from drf_spectacular.extensions import OpenApiAuthenticationExtension  # noqa: E402


class ApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.integrations.public_api.ApiKeyAuthentication"
    name = "ApiKeyAuth"

    def get_security_definition(self, auto_schema: Any) -> dict[str, str]:
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "Organisation API key: Authorization: Bearer mhrs_<prefix>_<secret>",
        }
