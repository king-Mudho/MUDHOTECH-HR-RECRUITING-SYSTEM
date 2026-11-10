from __future__ import annotations

from datetime import date
from typing import Any

from rest_framework import serializers

from apps.candidates import services
from apps.candidates.models import (
    CandidateProfile,
    CandidateSkill,
    Certification,
    Education,
    Experience,
    Language,
)
from apps.core.serializers import StrictModelSerializer


class LinksSerializer(serializers.Serializer):
    linkedin = serializers.URLField(required=False, allow_blank=True, max_length=300)
    github = serializers.URLField(required=False, allow_blank=True, max_length=300)
    portfolio = serializers.URLField(required=False, allow_blank=True, max_length=300)
    other = serializers.URLField(required=False, allow_blank=True, max_length=300)


class ProfileSerializer(StrictModelSerializer):
    links = LinksSerializer(required=False)
    missing = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email_verified = serializers.SerializerMethodField()
    lock_version = serializers.IntegerField(required=False)

    class Meta:
        model = CandidateProfile
        fields = [
            "id",
            "email",
            "email_verified",
            "first_name",
            "last_name",
            "preferred_name",
            "headline",
            "summary",
            "city",
            "country",
            "phone_e164",
            "links",
            "availability",
            "notice_period_days",
            "open_to_relocation",
            "profile_completeness",
            "missing",
            "lock_version",
            "updated_at",
        ]
        read_only_fields = ["id", "profile_completeness", "updated_at"]
        extra_kwargs = {"summary": {"max_length": 5000}}

    def get_missing(self, obj: CandidateProfile) -> list[str]:
        return services.completeness(obj)[1]

    def get_email_verified(self, obj: CandidateProfile) -> bool:
        return obj.user.email_verified_at is not None


class ItemSerializer(StrictModelSerializer):
    """Shared behaviour: ``source`` is read-only (CV imports go through a confirmation flow)."""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = attrs.get("start_date"), attrs.get("end_date")
        if self.instance is not None:
            start = start if "start_date" in attrs else getattr(self.instance, "start_date", None)
            end = end if "end_date" in attrs else getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": ["Must be on or after the start date."]})
        if start and start > date.today():
            raise serializers.ValidationError({"start_date": ["Must not be in the future."]})
        return attrs


class ExperienceSerializer(ItemSerializer):
    class Meta:
        model = Experience
        fields = [
            "id",
            "employer",
            "title",
            "location",
            "start_date",
            "end_date",
            "is_current",
            "description",
            "order",
            "source",
        ]
        read_only_fields = ["id", "source"]
        extra_kwargs = {"description": {"max_length": 5000}}

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        if attrs.get("is_current"):
            attrs["end_date"] = None
        return attrs


class EducationSerializer(ItemSerializer):
    class Meta:
        model = Education
        fields = [
            "id",
            "institution",
            "qualification_text",
            "qualification_level",
            "field",
            "start_date",
            "end_date",
            "grade",
            "order",
            "source",
        ]
        read_only_fields = ["id", "source"]


class CertificationSerializer(StrictModelSerializer):
    class Meta:
        model = Certification
        fields = [
            "id",
            "name",
            "body",
            "issued_at",
            "expires_at",
            "credential_id",
            "order",
            "source",
        ]
        read_only_fields = ["id", "source"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        issued, expires = attrs.get("issued_at"), attrs.get("expires_at")
        if issued and expires and expires < issued:
            raise serializers.ValidationError({"expires_at": ["Must be after the issue date."]})
        return attrs


class CandidateSkillSerializer(StrictModelSerializer):
    class Meta:
        model = CandidateSkill
        fields = ["id", "skill", "raw_name", "proficiency", "years", "order", "source"]
        read_only_fields = ["id", "source"]
        extra_kwargs = {"years": {"min_value": 0, "max_value": 60}}


class LanguageSerializer(StrictModelSerializer):
    class Meta:
        model = Language
        fields = ["id", "language", "proficiency", "order", "source"]
        read_only_fields = ["id", "source"]
