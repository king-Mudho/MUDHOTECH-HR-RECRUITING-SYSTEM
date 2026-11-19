"""Integrations API (P15-T01). Any staff member may connect their own calendar; organisation-wide
providers (SMS, WhatsApp) are managed by organisation admins. Credentials are write-only."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import PermissionDeniedError
from apps.organisations import rbac
from apps.organisations.permissions import HasOrgAction

from .. import messaging, public_api, registry, services, webhooks
from ..models import ApiKey, WebhookDelivery, WebhookEndpoint
from . import serializers as s

ALL_STAFF_ACTION = "org.view"


def body(conn: Any) -> dict[str, Any]:
    return {
        "id": conn.pk,
        "provider": conn.provider,
        "personal": conn.owner_user_id is not None,
        "credentials_hint": conn.credentials_hint,
        "config": conn.config or {},
        "status": conn.status,
        "sandbox": bool(conn.sandbox or settings.INTEGRATIONS_SANDBOX),
        "last_success_at": conn.last_success_at,
        "last_error_at": conn.last_error_at,
        "last_error": conn.last_error,
        "credentials_rotated_at": conn.credentials_rotated_at,
    }


class IntegrationsView(APIView):
    permission_classes = [HasOrgAction(ALL_STAFF_ACTION)]

    @extend_schema(operation_id="hr_integrations", responses=s.IntegrationsOverviewSerializer)
    def get(self, request: Request) -> Response:
        membership = request.membership  # type: ignore[attr-defined]
        manage = rbac.can(membership.role, "integrations.manage")
        providers = [
            {
                "key": p.key,
                "name": p.name,
                "kind": p.kind,
                "per_user": p.per_user,
                "credential_fields": list(p.credential_fields),
                "config_fields": list(p.config_fields),
                "docs": p.docs,
            }
            for p in registry.PROVIDERS.values()
            if p.per_user or manage
        ]
        rows = [body(c) for c in services.visible(membership).order_by("provider")]
        data = {
            "providers": providers,
            "connections": rows,
            "sandbox_default": settings.INTEGRATIONS_SANDBOX,
        }
        return Response(s.IntegrationsOverviewSerializer(data).data)

    @extend_schema(
        operation_id="hr_integrations_connect",
        request=s.ConnectSerializer,
        responses={201: s.ConnectionSerializer},
    )
    def post(self, request: Request) -> Response:
        membership = request.membership  # type: ignore[attr-defined]
        data = s.ConnectSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        provider = registry.PROVIDERS.get(v["provider"])
        if (
            provider is not None
            and not provider.per_user
            and not rbac.can(membership.role, "integrations.manage")
        ):
            raise PermissionDeniedError()
        conn = services.connect(
            membership,
            v["provider"],
            credentials=v["credentials"],
            config=v["config"],
            sandbox=v["sandbox"],
        )
        return Response(s.ConnectionSerializer(body(conn)).data, status=201)


class IntegrationView(APIView):
    permission_classes = [HasOrgAction(ALL_STAFF_ACTION)]

    @extend_schema(operation_id="hr_integration_disconnect", responses={204: None})
    def delete(self, request: Request, connection_id: str) -> Response:
        services.disconnect(request.membership, connection_id)  # type: ignore[attr-defined]
        return Response(status=204)


class IntegrationRotateView(APIView):
    permission_classes = [HasOrgAction(ALL_STAFF_ACTION)]

    @extend_schema(
        operation_id="hr_integration_rotate",
        request=s.RotateSerializer,
        responses=s.ConnectionSerializer,
    )
    def post(self, request: Request, connection_id: str) -> Response:
        data = s.RotateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        conn = services.rotate(
            request.membership,  # type: ignore[attr-defined]
            connection_id,
            data.validated_data["credentials"],
        )
        return Response(s.ConnectionSerializer(body(conn)).data)


class IntegrationTestView(APIView):
    permission_classes = [HasOrgAction(ALL_STAFF_ACTION)]

    @extend_schema(
        operation_id="hr_integration_test", request=None, responses=s.ConnectionSerializer
    )
    def post(self, request: Request, connection_id: str) -> Response:
        conn = services.test_connection(request.membership, connection_id)  # type: ignore[attr-defined]
        return Response(s.ConnectionSerializer(body(conn)).data)


# --- webhooks (P15-T05) ---------------------------------------------------------------------------
def _m(request: Request) -> Any:
    return request.membership  # type: ignore[attr-defined]


def _endpoint_body(e: Any, secret: str | None = None) -> dict[str, Any]:
    out = {
        "id": e.pk,
        "url": e.url,
        "events": e.events,
        "description": e.description,
        "active": e.active,
        "created_at": e.created_at,
    }
    if secret is not None:
        out["secret"] = secret
    return out


class WebhooksView(APIView):
    permission_classes = [HasOrgAction("integrations.manage")]

    @extend_schema(operation_id="hr_webhooks", responses=s.WebhooksOverviewSerializer)
    def get(self, request: Request) -> Response:
        org_id = _m(request).organisation_id
        endpoints = WebhookEndpoint.objects.for_org(org_id).order_by("created_at")
        deliveries = WebhookDelivery.objects.for_org(org_id).order_by("-created_at")[:50]
        data = {
            "events": list(webhooks.EVENTS),
            "endpoints": [_endpoint_body(e) for e in endpoints],
            "deliveries": deliveries,
        }
        return Response(s.WebhooksOverviewSerializer(data).data)

    @extend_schema(
        operation_id="hr_webhooks_create",
        request=s.WebhookEndpointInSerializer,
        responses={201: s.WebhookEndpointCreatedSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.WebhookEndpointInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        endpoint, secret = webhooks.create_endpoint(
            _m(request),
            **data.validated_data,
        )
        return Response(
            s.WebhookEndpointCreatedSerializer(_endpoint_body(endpoint, secret)).data, status=201
        )


class WebhookEndpointView(APIView):
    permission_classes = [HasOrgAction("integrations.manage")]

    @extend_schema(
        operation_id="hr_webhook_update",
        request=s.WebhookEndpointPatchSerializer,
        responses=s.WebhookEndpointSerializer,
    )
    def patch(self, request: Request, endpoint_id: str) -> Response:
        data = s.WebhookEndpointPatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        endpoint = webhooks.update_endpoint(
            _m(request),
            endpoint_id,
            **data.validated_data,
        )
        return Response(s.WebhookEndpointSerializer(_endpoint_body(endpoint)).data)

    @extend_schema(operation_id="hr_webhook_delete", responses={204: None})
    def delete(self, request: Request, endpoint_id: str) -> Response:
        webhooks.delete_endpoint(_m(request), endpoint_id)
        return Response(status=204)


class WebhookRotateView(APIView):
    permission_classes = [HasOrgAction("integrations.manage")]

    @extend_schema(
        operation_id="hr_webhook_rotate", request=None, responses=s.WebhookEndpointCreatedSerializer
    )
    def post(self, request: Request, endpoint_id: str) -> Response:
        endpoint, secret = webhooks.rotate_secret(
            _m(request),
            endpoint_id,
        )
        return Response(s.WebhookEndpointCreatedSerializer(_endpoint_body(endpoint, secret)).data)


class WebhookReplayView(APIView):
    permission_classes = [HasOrgAction("integrations.manage")]

    @extend_schema(
        operation_id="hr_webhook_delivery_replay",
        request=None,
        responses=s.WebhookDeliverySerializer,
    )
    def post(self, request: Request, delivery_id: str) -> Response:
        d = webhooks.replay(_m(request), delivery_id)
        return Response(s.WebhookDeliverySerializer(d).data)


# --- API keys, public API v1 and feeds (P15-T06) -----------------------------------------------
class ApiKeysView(APIView):
    permission_classes = [HasOrgAction("integrations.manage")]

    @extend_schema(operation_id="hr_api_keys", responses=s.ApiKeySerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = ApiKey.objects.for_org(_m(request).organisation_id).order_by("-created_at")
        return Response(s.ApiKeySerializer(rows, many=True).data)

    @extend_schema(
        operation_id="hr_api_keys_create",
        request=s.ApiKeyInSerializer,
        responses={201: s.ApiKeyCreatedSerializer},
    )
    def post(self, request: Request) -> Response:
        data = s.ApiKeyInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        key, token = public_api.create_key(_m(request), **data.validated_data)
        body_ = s.ApiKeySerializer(key).data
        return Response(s.ApiKeyCreatedSerializer({**body_, "key": token}).data, status=201)


class ApiKeyView(APIView):
    permission_classes = [HasOrgAction("integrations.manage")]

    @extend_schema(operation_id="hr_api_key_revoke", request=None, responses=s.ApiKeySerializer)
    def delete(self, request: Request, key_id: str) -> Response:
        return Response(s.ApiKeySerializer(public_api.revoke_key(_m(request), key_id)).data)


class PublicApiJobsView(APIView):
    authentication_classes = [public_api.ApiKeyAuthentication]
    permission_classes = [public_api.HasScope("jobs:read")]
    throttle_classes = [public_api.ApiKeyThrottle]

    @extend_schema(
        operation_id="public_api_jobs",
        tags=["public-api"],
        responses=s.PublicJobSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        from apps.organisations.models import Organisation

        org = Organisation.objects.get(pk=request.auth.organisation_id)  # type: ignore[union-attr]
        return Response(s.PublicJobSerializer(public_api.feed_jobs(org.slug), many=True).data)


class PublicApiApplicationsView(APIView):
    authentication_classes = [public_api.ApiKeyAuthentication]
    permission_classes = [public_api.HasScope("applications:read")]
    throttle_classes = [public_api.ApiKeyThrottle]

    @extend_schema(
        operation_id="public_api_applications",
        tags=["public-api"],
        responses=s.PublicApplicationSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        from apps.applications.models import Application

        org_id = request.auth.organisation_id  # type: ignore[union-attr]
        qs = (
            Application.objects.for_org(org_id)
            .exclude(submitted_at__isnull=True)
            .order_by("-updated_at")
        )
        if request.query_params.get("job"):
            qs = qs.filter(job_id=request.query_params["job"])
        since = request.query_params.get("updated_since")
        if since:
            from django.utils.dateparse import parse_datetime

            moment = parse_datetime(since)
            if moment is not None:
                qs = qs.filter(updated_at__gte=moment)
        rows = qs.values("id", "reference", "job_id", "status", "submitted_at", "updated_at")[:500]
        return Response(s.PublicApplicationSerializer(list(rows), many=True).data)


class JobsFeedXmlView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="feeds_jobs_xml",
        tags=["public-api"],
        responses={(200, "application/xml"): OpenApiResponse(description="Job feed (XML)")},
    )
    def get(self, request: Request, org_slug: str) -> HttpResponse:
        response = HttpResponse(public_api.jobs_xml(org_slug), content_type="application/xml")
        response["Cache-Control"] = "public, max-age=300"
        return response


class JobsFeedJsonView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="feeds_jobs_json",
        tags=["public-api"],
        responses=s.PublicJobSerializer(many=True),
    )
    def get(self, request: Request, org_slug: str) -> Response:
        response = Response(s.PublicJobSerializer(public_api.feed_jobs(org_slug), many=True).data)
        response["Cache-Control"] = "public, max-age=300"
        return response


# --- SMS / WhatsApp (P15-T04) -------------------------------------------------------------------
class CandidateMessagingView(APIView):
    from rest_framework.permissions import IsAuthenticated

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_messaging_preferences", responses=s.MessagingPreferencesSerializer
    )
    def get(self, request: Request) -> Response:
        user = request.user
        data = {
            "sms": messaging.has_consent(user, "sms"),
            "whatsapp": messaging.has_consent(user, "whatsapp"),
        }
        return Response(s.MessagingPreferencesSerializer(data).data)

    @extend_schema(
        operation_id="candidate_messaging_preferences_update",
        request=s.MessagingPreferencesSerializer,
        responses=s.MessagingPreferencesSerializer,
    )
    def put(self, request: Request) -> Response:
        data = s.MessagingPreferencesSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        out = messaging.set_preferences(
            request.user, ip=request.META.get("REMOTE_ADDR"), **data.validated_data
        )
        return Response(s.MessagingPreferencesSerializer(out).data)


def _shared_secret_ok(request: Request) -> bool:
    import hmac as _hmac

    expected = settings.SMS_WEBHOOK_SECRET
    given = request.META.get("HTTP_X_MHRS_WEBHOOK_SECRET", "")
    return bool(expected) and _hmac.compare_digest(expected, given)


@method_decorator(csrf_exempt, name="dispatch")
class SmsReceiptView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="integrations_sms_receipt", request=None, responses={200: None})
    def post(self, request: Request) -> Response:
        if not _shared_secret_ok(request):
            return Response(status=403)
        data = request.data if isinstance(request.data, dict) else {}
        messaging.record_receipt(str(data.get("id", "")), str(data.get("status", "")))
        return Response(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class SmsInboundView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="integrations_sms_inbound", request=None, responses={200: None})
    def post(self, request: Request) -> Response:
        if not _shared_secret_ok(request):
            return Response(status=403)
        data = request.data if isinstance(request.data, dict) else {}
        if str(data.get("text", "")).strip().upper() in messaging.STOP_WORDS:
            messaging.opt_out(str(data.get("from", "")), "sms", "sms_stop")
        return Response(status=200)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(APIView):
    """Meta webhook: GET verification handshake, POST signed with the app secret."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    @extend_schema(operation_id="integrations_whatsapp_verify", responses={200: None})
    def get(self, request: Request) -> HttpResponse:
        q = request.query_params
        token = settings.WHATSAPP_VERIFY_TOKEN
        if token and q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == token:
            return HttpResponse(q.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)

    @extend_schema(operation_id="integrations_whatsapp_event", request=None, responses={200: None})
    def post(self, request: Request) -> Response:
        import hashlib as _hashlib
        import hmac as _hmac
        import json as _json

        secret = settings.WHATSAPP_APP_SECRET
        body = request.body
        given = request.META.get("HTTP_X_HUB_SIGNATURE_256", "")
        expected = "sha256=" + _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
        if not secret or not _hmac.compare_digest(expected, given):
            return Response(status=403)
        try:
            payload = _json.loads(body.decode() or "{}")
        except ValueError:
            return Response(status=200)
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    text = str(msg.get("text", {}).get("body", "")).strip().upper()
                    if text in messaging.STOP_WORDS:
                        messaging.opt_out(str(msg.get("from", "")), "whatsapp", "whatsapp_stop")
                for st in value.get("statuses", []):
                    messaging.record_receipt(str(st.get("id", "")), str(st.get("status", "")))
        return Response(status=200)
