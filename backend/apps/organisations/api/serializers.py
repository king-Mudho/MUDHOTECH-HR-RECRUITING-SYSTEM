from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.accounts.models import User
from apps.core.serializers import StrictModelSerializer, StrictSerializer
from apps.organisations.models import (
    Department,
    Invitation,
    Location,
    Membership,
    Organisation,
    OrganisationPolicy,
    Role,
)
from apps.organisations.services import ORG_EDITABLE_FIELDS, POLICY_EDITABLE_FIELDS


class OrganisationSerializer(StrictModelSerializer):
    my_role = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        fields = [
            "id",
            "slug",
            "status",
            "verified_at",
            "logo_key",
            "created_at",
            "my_role",
            "logo_url",
            *ORG_EDITABLE_FIELDS,
        ]
        read_only_fields = ["id", "slug", "status", "verified_at", "logo_key", "created_at"]
        extra_kwargs = {"name": {"required": True}}

    def get_logo_url(self, obj: Organisation) -> str | None:
        from apps.organisations.logo import logo_url

        return logo_url(obj)

    def get_my_role(self, obj: Organisation) -> str | None:
        membership = getattr(self.context.get("request"), "membership", None)
        return membership.role if membership and membership.organisation_id == obj.pk else None


class OrganisationCreateSerializer(OrganisationSerializer):
    class Meta(OrganisationSerializer.Meta):
        extra_kwargs = {"name": {"required": True, "allow_blank": False}}


class PublicCompanySerializer(serializers.ModelSerializer):
    open_jobs = serializers.SerializerMethodField()
    logo_url = serializers.SerializerMethodField()

    def get_logo_url(self, obj: Organisation) -> str | None:
        from apps.organisations.logo import logo_url

        return logo_url(obj)

    class Meta:
        model = Organisation
        fields = [
            "slug",
            "name",
            "description",
            "industry",
            "city",
            "country",
            "website",
            "logo_url",
            "size_band",
            "open_jobs",
        ]

    def get_open_jobs(self, obj: Organisation) -> list[dict[str, Any]]:
        return []  # populated by the jobs app in Phase 03


class PolicySerializer(StrictModelSerializer):
    lock_version = serializers.IntegerField(write_only=True)

    class Meta:
        model = OrganisationPolicy
        fields = ["version", "lock_version", *POLICY_EDITABLE_FIELDS]
        read_only_fields = ["version"]


class DepartmentSerializer(StrictModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        org = getattr(self.context.get("request"), "organisation", None)
        if org is not None:
            qs = Department.objects.for_org(org).filter(name__iexact=value)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError("A department with this name already exists.")
        return value


class LocationSerializer(StrictModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "city", "country", "workplace_type_default", "created_at"]
        read_only_fields = ["id", "created_at"]


class MemberUserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "display_name"]


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)
    mfa_enabled = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = [
            "id",
            "organisation_id",
            "user",
            "role",
            "status",
            "joined_at",
            "deactivated_at",
            "mfa_enabled",
        ]
        read_only_fields = fields

    def get_mfa_enabled(self, obj: Membership) -> bool:
        from apps.accounts.mfa import has_mfa

        return has_mfa(obj.user)


class MembershipUpdateSerializer(StrictSerializer):
    role = serializers.ChoiceField(choices=Role.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ReasonSerializer(StrictSerializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class RequiredReasonSerializer(StrictSerializer):
    reason = serializers.CharField(min_length=10, max_length=500)


class DeactivationSerializer(serializers.Serializer):
    membership = MembershipSerializer()
    sessions_revoked = serializers.IntegerField()
    needs_reassignment = serializers.ListField(child=serializers.DictField())


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    invited_by = MemberUserSerializer(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "role",
            "status",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "invited_by",
            "vacancy_ids",
            "allow_any_email",
            "created_at",
        ]


class InvitationCreateSerializer(StrictSerializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices)
    vacancy_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    allow_any_email = serializers.BooleanField(required=False, default=False)


class InvitationPublicSerializer(serializers.Serializer):
    """What an invitee sees before signing in (no token, partially masked email)."""

    organisation_name = serializers.CharField()
    organisation_slug = serializers.CharField()
    role = serializers.CharField()
    email_hint = serializers.CharField()
    status = serializers.CharField()
    expires_at = serializers.DateTimeField()

    @staticmethod
    def build(inv: Invitation) -> dict[str, Any]:
        local, _, domain = inv.email.partition("@")
        hint = f"{local[:2]}{'*' * max(len(local) - 2, 1)}@{domain}"
        return {
            "organisation_name": inv.organisation.name,
            "organisation_slug": inv.organisation.slug,
            "role": inv.role,
            "email_hint": hint,
            "status": inv.status,
            "expires_at": inv.expires_at,
        }


class LogoUploadSerializer(serializers.Serializer):
    logo = serializers.FileField()
