"""GET/PATCH /me - the signed-in user's profile, memberships, active org and MFA status."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import phonenumbers
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.mfa import mfa_status
from apps.accounts.models import User
from apps.accounts.services import authed_user
from apps.audit import services as audit
from apps.core.serializers import StrictModelSerializer
from apps.organisations.selectors import memberships_for_user


class MeMembershipSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organisation_id = serializers.UUIDField()
    organisation_name = serializers.CharField(source="organisation.name")
    organisation_slug = serializers.CharField(source="organisation.slug")
    organisation_status = serializers.CharField(source="organisation.status")
    role = serializers.CharField()


class MfaStatusSerializer(serializers.Serializer):
    # A field named "required" shadows Field.required for type checkers only (DRF pops it).
    required = serializers.BooleanField()  # type: ignore[assignment]
    enabled = serializers.BooleanField()
    grace_deadline = serializers.DateTimeField(allow_null=True)
    in_grace = serializers.BooleanField()
    enforced = serializers.BooleanField()


class MeSerializer(StrictModelSerializer):
    email_verified = serializers.BooleanField(source="is_email_verified", read_only=True)
    display_name = serializers.CharField(read_only=True)
    memberships = serializers.SerializerMethodField()
    active_organisation_id = serializers.SerializerMethodField()
    mfa = serializers.SerializerMethodField()
    candidate_profile_id = serializers.SerializerMethodField()
    email_delivery_problem = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "email_verified",
            "first_name",
            "last_name",
            "preferred_name",
            "display_name",
            "phone_e164",
            "locale",
            "timezone",
            "platform_role",
            "memberships",
            "active_organisation_id",
            "mfa",
            "candidate_profile_id",
            "email_delivery_problem",
        ]
        read_only_fields = ["id", "email", "platform_role"]

    def get_email_delivery_problem(self, obj: User) -> bool:
        """EC-NOT-01: emails to this address bounced - the UI asks the person to update it."""
        from apps.notifications.bounces import has_delivery_problem

        return has_delivery_problem(obj)

    @extend_schema_field(MeMembershipSerializer(many=True))
    def get_memberships(self, obj: User) -> list[dict[str, Any]]:
        return MeMembershipSerializer(memberships_for_user(obj), many=True).data  # type: ignore[return-value]

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_active_organisation_id(self, obj: User) -> str | None:
        org = getattr(self.context["request"], "organisation", None)
        return str(org.pk) if org else None

    @extend_schema_field(MfaStatusSerializer)
    def get_mfa(self, obj: User) -> dict[str, Any]:
        return mfa_status(obj).as_dict()

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_candidate_profile_id(self, obj: User) -> str | None:
        return None  # candidate profiles arrive in Phase 04

    def validate_phone_e164(self, value: str) -> str:
        if not value:
            return ""
        try:
            parsed = phonenumbers.parse(value, "ZW")
        except phonenumbers.NumberParseException as exc:
            raise serializers.ValidationError("Enter a valid phone number.") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise serializers.ValidationError("Enter a valid phone number.")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

    def validate_timezone(self, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("Unknown time zone.") from exc
        return value

    def validate_locale(self, value: str) -> str:
        if value not in ("en", "sn", "nd"):
            raise serializers.ValidationError("Unsupported language.")
        return value


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="me_retrieve", responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(authed_user(request), context={"request": request}).data)

    @extend_schema(operation_id="me_update", request=MeSerializer, responses=MeSerializer)
    def patch(self, request: Request) -> Response:
        user = authed_user(request)
        ser = MeSerializer(user, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        before = {k: getattr(user, k) for k in ser.validated_data}
        ser.save()
        audit.record(
            actor=user,
            action="user.profile_updated",
            target=user,
            before=before,
            after=dict(ser.validated_data),
            request=request,
        )
        return Response(MeSerializer(user, context={"request": request}).data)
