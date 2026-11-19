from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer


class ProviderSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    per_user = serializers.BooleanField()
    credential_fields = serializers.ListField(child=serializers.CharField())
    config_fields = serializers.ListField(child=serializers.CharField())
    docs = serializers.CharField()


class ConnectionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.CharField()
    personal = serializers.BooleanField()
    credentials_hint = serializers.CharField()
    config = serializers.DictField()
    status = serializers.CharField()
    sandbox = serializers.BooleanField()
    last_success_at = serializers.DateTimeField(allow_null=True)
    last_error_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField(allow_blank=True)
    credentials_rotated_at = serializers.DateTimeField(allow_null=True)


class IntegrationsOverviewSerializer(serializers.Serializer):
    providers = ProviderSerializer(many=True)
    connections = ConnectionSerializer(many=True)
    sandbox_default = serializers.BooleanField()


class ConnectSerializer(StrictSerializer):
    provider = serializers.CharField(max_length=40)
    credentials = serializers.DictField(child=serializers.CharField(max_length=4000))
    config = serializers.DictField(
        child=serializers.CharField(max_length=200), required=False, default=dict
    )
    sandbox = serializers.BooleanField(required=False, default=False)


class RotateSerializer(StrictSerializer):
    credentials = serializers.DictField(child=serializers.CharField(max_length=4000))


class WebhookEndpointSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    url = serializers.URLField()
    events = serializers.ListField(child=serializers.CharField())
    description = serializers.CharField(allow_blank=True)
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class WebhookEndpointCreatedSerializer(WebhookEndpointSerializer):
    secret = serializers.CharField(help_text="Shown once; store it to verify signatures.")


class WebhookEndpointInSerializer(StrictSerializer):
    url = serializers.URLField(max_length=500)
    events = serializers.ListField(child=serializers.CharField(max_length=100), min_length=1)
    description = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )


class WebhookEndpointPatchSerializer(StrictSerializer):
    events = serializers.ListField(child=serializers.CharField(max_length=100), required=False)
    active = serializers.BooleanField(required=False)


class WebhookDeliverySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    endpoint_id = serializers.UUIDField()
    event_type = serializers.CharField()
    status = serializers.CharField()
    attempts = serializers.IntegerField()
    response_code = serializers.IntegerField(allow_null=True)
    last_error = serializers.CharField(allow_blank=True)
    next_attempt_at = serializers.DateTimeField(allow_null=True)
    delivered_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class WebhooksOverviewSerializer(serializers.Serializer):
    events = serializers.ListField(child=serializers.CharField())
    endpoints = WebhookEndpointSerializer(many=True)
    deliveries = WebhookDeliverySerializer(many=True)


class ApiKeySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    prefix = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    last_used_at = serializers.DateTimeField(allow_null=True)
    revoked_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class ApiKeyCreatedSerializer(ApiKeySerializer):
    key = serializers.CharField(help_text="Shown once.")


class ApiKeyInSerializer(StrictSerializer):
    name = serializers.CharField(max_length=80)
    scopes = serializers.ListField(child=serializers.CharField(max_length=40), min_length=1)


class PublicJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    company = serializers.CharField()
    url = serializers.URLField()
    apply_url = serializers.URLField()
    city = serializers.CharField(allow_blank=True)
    country = serializers.CharField()
    employment_type = serializers.CharField(allow_blank=True, allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    closes_at = serializers.DateTimeField(allow_null=True)
    summary = serializers.CharField(allow_blank=True)


class PublicApplicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField()


class MessagingPreferencesSerializer(StrictSerializer):
    sms = serializers.BooleanField()
    whatsapp = serializers.BooleanField()
