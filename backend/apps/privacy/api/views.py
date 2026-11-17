"""Privacy endpoints (P09-T02; docs/04 Privacy & audit).

Candidates: their consents and rights requests (re-auth + email confirmation).
Organisation admins: requests routed to their organisation, legal holds.
Platform admins: account-level requests (``organisation`` NULL).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.audit import services as audit
from apps.core.exceptions import NotFoundError
from apps.core.serializers import StrictSerializer
from apps.core.time import now
from apps.organisations.permissions import HasOrgAction, IsPlatformAdmin

from .. import rights, services
from ..models import ConsentRecord, LegalHold, RightsRequest


# ------------------------------------------------------------------------ serializers
class RightsRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reference = serializers.CharField()
    type = serializers.CharField()
    status = serializers.CharField()
    organisation_id = serializers.UUIDField(allow_null=True)
    organisation_name = serializers.CharField()
    details = serializers.CharField(allow_blank=True)
    resolution = serializers.CharField(allow_blank=True)
    statement = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    verified_at = serializers.DateTimeField(allow_null=True)
    due_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    export_available = serializers.BooleanField()


class StaffRightsRequestSerializer(RightsRequestSerializer):
    requester = serializers.CharField(allow_null=True)
    handled_by = serializers.CharField(allow_null=True)
    overdue = serializers.BooleanField()


class CreateRightsRequestSerializer(StrictSerializer):
    type = serializers.ChoiceField(choices=RightsRequest.Type.choices)
    scope = serializers.ChoiceField(choices=["organisation", "platform", "all"])
    organisation_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    details = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)
    password = serializers.CharField(write_only=True, max_length=200)


class ConfirmSerializer(StrictSerializer):
    token = serializers.CharField(max_length=200)


class StatementSerializer(StrictSerializer):
    statement = serializers.CharField(max_length=4000)


class ActionSerializer(StrictSerializer):
    action = serializers.ChoiceField(choices=list(rights.ACTIONS))
    resolution = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=4000
    )


class EmployerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class ConsentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    purpose = serializers.CharField()
    organisation_id = serializers.UUIDField(allow_null=True)
    organisation_name = serializers.CharField(allow_null=True)
    notice_version = serializers.CharField()
    granted = serializers.BooleanField()
    granted_at = serializers.DateTimeField()
    withdrawn_at = serializers.DateTimeField(allow_null=True)


class LegalHoldSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    target_type = serializers.ChoiceField(choices=LegalHold.Target.choices)
    target_id = serializers.UUIDField()
    reason = serializers.CharField(max_length=2000, write_only=True)
    placed_at = serializers.DateTimeField(read_only=True)
    released_at = serializers.DateTimeField(read_only=True, allow_null=True)


def _names(ids: set[Any]) -> dict[Any, str]:
    from apps.organisations.models import Organisation

    return dict(Organisation.objects.filter(pk__in=[i for i in ids if i]).values_list("pk", "name"))


def _shape(rows: list[RightsRequest], *, staff: bool = False) -> list[dict[str, Any]]:
    names = _names({r.organisation_id for r in rows})
    out = []
    for r in rows:
        body: dict[str, Any] = {
            "id": r.pk,
            "reference": r.reference,
            "type": r.type,
            "status": r.status,
            "organisation_id": r.organisation_id,
            "organisation_name": names.get(r.organisation_id, "MUDHOTECH HR RECRUITING SYSTEM"),
            "details": r.details,
            "resolution": r.resolution,
            "statement": r.statement,
            "created_at": r.created_at,
            "verified_at": r.verified_at,
            "due_at": r.due_at,
            "completed_at": r.completed_at,
            "export_available": bool(
                r.export_document_id and r.export_expires_at and r.export_expires_at > now()
            ),
        }
        if staff:
            body |= {
                "requester": r.user.email if r.user else None,
                "handled_by": r.handled_by.email if r.handled_by else None,
                "overdue": r.status not in ("completed", "declined") and r.due_at < now(),
            }
        out.append(body)
    return out


# ------------------------------------------------------------------------ candidate
class MyRightsRequestsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="privacy_requests_list", responses=RightsRequestSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = list(rights.mine(authed_user(request)))
        return Response(RightsRequestSerializer(_shape(rows), many=True).data)

    @extend_schema(
        operation_id="privacy_requests_create",
        request=CreateRightsRequestSerializer,
        responses={201: RightsRequestSerializer(many=True)},
    )
    def post(self, request: Request) -> Response:
        data = CreateRightsRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        rows = rights.create(authed_user(request), **data.validated_data)
        return Response(RightsRequestSerializer(_shape(rows), many=True).data, status=201)


class ConfirmRightsRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="privacy_requests_confirm",
        request=ConfirmSerializer,
        responses=RightsRequestSerializer(many=True),
    )
    def post(self, request: Request) -> Response:
        data = ConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        rows = rights.confirm(authed_user(request), data.validated_data["token"])
        return Response(RightsRequestSerializer(_shape(rows), many=True).data)


class RightsStatementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="privacy_request_statement",
        request=StatementSerializer,
        responses=RightsRequestSerializer,
    )
    def post(self, request: Request, request_id: str) -> Response:
        data = StatementSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = rights.add_statement(
            authed_user(request), request_id, data.validated_data["statement"]
        )
        return Response(RightsRequestSerializer(_shape([row])[0]).data)


class MyEmployersView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="privacy_employers", responses=EmployerSerializer(many=True))
    def get(self, request: Request) -> Response:
        ids = rights.employers_of(authed_user(request))
        names = _names(set(ids))
        return Response(
            EmployerSerializer([{"id": i, "name": names.get(i, "")} for i in ids], many=True).data
        )


class MyConsentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="privacy_consents", responses=ConsentSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = list(ConsentRecord.objects.filter(user=authed_user(request)).order_by("-granted_at"))
        names = _names({r.organisation_id for r in rows})
        body = [
            {
                "id": r.pk,
                "purpose": r.purpose,
                "organisation_id": r.organisation_id,
                "organisation_name": names.get(r.organisation_id),
                "notice_version": r.notice_version,
                "granted": r.granted,
                "granted_at": r.granted_at,
                "withdrawn_at": r.withdrawn_at,
            }
            for r in rows
        ]
        return Response(ConsentSerializer(body, many=True).data)


class WithdrawConsentView(APIView):
    """Withdrawal is immediate and never retroactive (CDPA); the employer is told via audit."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="privacy_consent_withdraw", request=None, responses=ConsentSerializer
    )
    def post(self, request: Request, consent_id: str) -> Response:
        user = authed_user(request)
        with transaction.atomic():
            row = (
                ConsentRecord.objects.select_for_update()
                .filter(pk=consent_id, user=user, granted=True, withdrawn_at__isnull=True)
                .first()
            )
            if row is None:
                raise NotFoundError()
            row.withdrawn_at = now()
            row.save(update_fields=["withdrawn_at", "updated_at"])
            audit.record(
                actor=user,
                action="privacy.consent_withdrawn",
                target=("consent", str(row.pk)),
                organisation=row.organisation_id,
                after={"purpose": row.purpose},
            )
        return Response(
            ConsentSerializer(
                {
                    "id": row.pk,
                    "purpose": row.purpose,
                    "organisation_id": row.organisation_id,
                    "organisation_name": _names({row.organisation_id}).get(row.organisation_id),
                    "notice_version": row.notice_version,
                    "granted": row.granted,
                    "granted_at": row.granted_at,
                    "withdrawn_at": row.withdrawn_at,
                }
            ).data
        )


# ------------------------------------------------------------------------ organisation admins
class HRRightsRequestsView(APIView):
    permission_classes = [HasOrgAction("privacy.manage")]

    @extend_schema(
        operation_id="hr_privacy_requests", responses=StaffRightsRequestSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = list(
            rights.for_org(request.membership.organisation_id)  # type: ignore[attr-defined]
            .select_related("user", "handled_by")
            .order_by("due_at")[:500]
        )
        return Response(StaffRightsRequestSerializer(_shape(rows, staff=True), many=True).data)


class HRRightsRequestActionView(APIView):
    permission_classes = [HasOrgAction("privacy.manage")]

    @extend_schema(
        operation_id="hr_privacy_request_action",
        request=ActionSerializer,
        responses=StaffRightsRequestSerializer,
    )
    def post(self, request: Request, request_id: str) -> Response:
        data = ActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = rights.act(
            request.membership.organisation_id,  # type: ignore[attr-defined]
            authed_user(request),
            request_id,
            **data.validated_data,
        )
        return Response(StaffRightsRequestSerializer(_shape([row], staff=True)[0]).data)


class HRLegalHoldsView(APIView):
    permission_classes = [HasOrgAction("privacy.manage")]

    @extend_schema(operation_id="hr_legal_holds", responses=LegalHoldSerializer(many=True))
    def get(self, request: Request) -> Response:
        rows = LegalHold.objects.for_org(request.membership.organisation_id)[:500]  # type: ignore[attr-defined]
        return Response(LegalHoldSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="hr_legal_hold_place",
        request=LegalHoldSerializer,
        responses={201: LegalHoldSerializer},
    )
    def post(self, request: Request) -> Response:
        data = LegalHoldSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        hold = services.place_hold(
            request.membership.organisation_id,  # type: ignore[attr-defined]
            authed_user(request),
            **data.validated_data,
        )
        return Response(LegalHoldSerializer(hold).data, status=status.HTTP_201_CREATED)


class HRLegalHoldReleaseView(APIView):
    permission_classes = [HasOrgAction("privacy.manage")]

    @extend_schema(
        operation_id="hr_legal_hold_release", request=None, responses=LegalHoldSerializer
    )
    def post(self, request: Request, hold_id: str) -> Response:
        hold = services.release_hold(
            request.membership.organisation_id,  # type: ignore[attr-defined]
            authed_user(request),
            hold_id,
        )
        return Response(LegalHoldSerializer(hold).data)


# ------------------------------------------------------------------------ platform admins
class PlatformRightsRequestsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_privacy_requests", responses=StaffRightsRequestSerializer(many=True)
    )
    def get(self, request: Request) -> Response:
        rows = list(
            rights.for_org(None).select_related("user", "handled_by").order_by("due_at")[:500]
        )
        return Response(StaffRightsRequestSerializer(_shape(rows, staff=True), many=True).data)


class PlatformRightsRequestActionView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_privacy_request_action",
        request=ActionSerializer,
        responses=StaffRightsRequestSerializer,
    )
    def post(self, request: Request, request_id: str) -> Response:
        data = ActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = rights.act(None, authed_user(request), request_id, **data.validated_data)
        return Response(StaffRightsRequestSerializer(_shape([row], staff=True)[0]).data)
