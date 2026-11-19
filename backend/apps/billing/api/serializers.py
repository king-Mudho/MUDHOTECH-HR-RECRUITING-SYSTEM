from __future__ import annotations

from rest_framework import serializers


class BillingPlanSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    limits = serializers.DictField(child=serializers.IntegerField(allow_null=True))
    price_usd = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    price_zwg = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    interval = serializers.CharField()
    is_trial = serializers.BooleanField()


class SubscriptionInfoSerializer(serializers.Serializer):
    status = serializers.CharField()
    currency = serializers.CharField()
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    current_period_end = serializers.DateTimeField(allow_null=True)
    grace_until = serializers.DateTimeField(allow_null=True)


class UsageMetricSerializer(serializers.Serializer):
    metric = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    used = serializers.FloatField()
    limit = serializers.IntegerField(allow_null=True)


class UsageMonthSerializer(serializers.Serializer):
    period = serializers.DateField()
    values = serializers.DictField(child=serializers.IntegerField())


class BillingOverviewSerializer(serializers.Serializer):
    plan = BillingPlanSerializer()
    subscription = SubscriptionInfoSerializer()
    usage = UsageMetricSerializer(many=True)
    history = UsageMonthSerializer(many=True)
    plans = BillingPlanSerializer(many=True)
