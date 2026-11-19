from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer


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


class InvoiceLineSerializer(serializers.Serializer):
    description = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)


class InvoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    currency = serializers.CharField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    status = serializers.CharField()
    lines = InvoiceLineSerializer(many=True)
    period_start = serializers.DateField(allow_null=True)
    period_end = serializers.DateField(allow_null=True)
    issued_at = serializers.DateTimeField(allow_null=True)
    due_at = serializers.DateTimeField(allow_null=True)
    paid_at = serializers.DateTimeField(allow_null=True)


class PayRequestSerializer(StrictSerializer):
    method = serializers.ChoiceField(choices=["card", "ecocash", "onemoney"])
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class PaymentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    invoice_id = serializers.UUIDField()
    reference = serializers.CharField()
    method = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    paid_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class PayResultSerializer(serializers.Serializer):
    payment = PaymentSerializer()
    redirect_url = serializers.CharField(allow_blank=True)
    instructions = serializers.CharField(allow_blank=True)


class ManualPaymentSerializer(StrictSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(max_length=100)
