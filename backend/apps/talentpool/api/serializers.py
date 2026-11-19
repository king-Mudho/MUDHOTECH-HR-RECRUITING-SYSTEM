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
