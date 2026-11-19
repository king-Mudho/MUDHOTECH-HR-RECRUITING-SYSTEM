from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class TalentPoolMembershipSerializer(serializers.Serializer):
    organisation_id = serializers.UUIDField()
    organisation_name = serializers.CharField()
    status = serializers.ChoiceField(choices=["none", "active", "expired", "withdrawn"])
    joined_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    reconfirm_due = serializers.BooleanField()


class TalentPoolJoinSerializer(StrictSerializer):
    organisation_id = serializers.UUIDField()


class TalentPoolLeaveSerializer(StrictSerializer):
    delete = serializers.BooleanField(required=False, default=False)


class TalentApplicationRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)
    job_title = serializers.CharField()


class TalentCandidateSerializer(serializers.Serializer):
    """A pool member as HR sees them: profile facts only, never documents (M18 AC)."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    headline = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    skills = serializers.ListField(child=serializers.CharField())
    qualifications = serializers.ListField(child=serializers.CharField())
    latest_title = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    joined_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    latest_application = TalentApplicationRefSerializer(allow_null=True)
    invited_job_ids = serializers.ListField(child=serializers.UUIDField())


PaginatedTalentCandidateSerializer = type(
    "PaginatedTalentCandidateList",
    (serializers.Serializer,),
    {
        "count": serializers.IntegerField(),
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": TalentCandidateSerializer(many=True),
    },
)


class TalentTagsSerializer(StrictSerializer):
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40, allow_blank=True), max_length=10
    )


class TalentInviteSerializer(StrictSerializer):
    job_id = serializers.UUIDField()


class TalentInviteResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    invited_at = serializers.DateTimeField()
