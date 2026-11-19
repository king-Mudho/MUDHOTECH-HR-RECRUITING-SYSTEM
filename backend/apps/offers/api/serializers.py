"""Offer API serializers (P12-T06)."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import StrictSerializer
from apps.jobs.models import Currency, EmploymentType, SalaryPeriod


class OfferTermsSerializer(StrictSerializer):
    salary_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    currency = serializers.ChoiceField(choices=Currency.choices)
    period = serializers.ChoiceField(choices=SalaryPeriod.choices)
    start_date = serializers.DateField()
    contract_type = serializers.ChoiceField(choices=EmploymentType.choices)
    conditions = serializers.CharField(
        max_length=10000, required=False, allow_blank=True, default=""
    )
    expires_at = serializers.DateTimeField()


class OfferPatchSerializer(StrictSerializer):
    lock_version = serializers.IntegerField()
    salary_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )
    currency = serializers.ChoiceField(choices=Currency.choices, required=False)
    period = serializers.ChoiceField(choices=SalaryPeriod.choices, required=False)
    start_date = serializers.DateField(required=False)
    contract_type = serializers.ChoiceField(choices=EmploymentType.choices, required=False)
    conditions = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    expires_at = serializers.DateTimeField(required=False)


class OfferCommentSerializer(StrictSerializer):
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class OfferRequiredCommentSerializer(StrictSerializer):
    comment = serializers.CharField(max_length=2000)


class OfferReasonSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=500)


class OfferHireSerializer(StrictSerializer):
    start_date = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=400, required=False, allow_blank=True, default="")


class CloseoutConfirmSerializer(StrictSerializer):
    fingerprint = serializers.CharField(max_length=64)
    reason_code = serializers.CharField(max_length=40, default="position_filled")
    reason_text = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class OfferAcceptSerializer(StrictSerializer):
    typed_name = serializers.CharField(max_length=200)
    agree = serializers.BooleanField()
    counter_offer_note = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class OfferDeclineSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


# --- output ---------------------------------------------------------------------------------------
class OfferApprovalSerializer(serializers.Serializer):
    approver = serializers.CharField()
    round = serializers.IntegerField()
    decision = serializers.CharField()
    comment = serializers.CharField(allow_blank=True)
    at = serializers.DateTimeField()


class OfferOpeningsSerializer(serializers.Serializer):
    openings = serializers.IntegerField()
    accepted = serializers.IntegerField()
    hired = serializers.IntegerField()
    remaining = serializers.IntegerField()
    over = serializers.BooleanField()


class OfferSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    application_id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)
    job_id = serializers.UUIDField()
    job_title = serializers.CharField()
    status = serializers.CharField()
    salary_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    period = serializers.CharField()
    start_date = serializers.DateField()
    contract_type = serializers.CharField()
    conditions = serializers.CharField(allow_blank=True)
    expires_at = serializers.DateTimeField()
    required_approvals = serializers.IntegerField()
    approval_round = serializers.IntegerField()
    approvals = OfferApprovalSerializer(many=True)
    created_by = serializers.CharField(allow_null=True)
    issued_at = serializers.DateTimeField(allow_null=True)
    accepted_at = serializers.DateTimeField(allow_null=True)
    counter_offer_note = serializers.CharField(allow_blank=True)
    declined_at = serializers.DateTimeField(allow_null=True)
    decline_reason = serializers.CharField(allow_blank=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    close_reason = serializers.CharField(allow_blank=True)
    has_letter = serializers.BooleanField()
    hire_recorded = serializers.BooleanField()
    lock_version = serializers.IntegerField()
    openings = OfferOpeningsSerializer()


class AcceptResultSerializer(serializers.Serializer):
    status = serializers.CharField()
    accepted_at = serializers.DateTimeField()


class HireResultSerializer(serializers.Serializer):
    hire_id = serializers.UUIDField()
    start_date = serializers.DateField()
    openings = OfferOpeningsSerializer()
    prompt_close = serializers.BooleanField()


class CloseoutRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)


class CloseoutPreviewSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    openings = OfferOpeningsSerializer()
    to_notify = serializers.IntegerField()
    to_notify_by_status = serializers.DictField(child=serializers.IntegerField())
    still_in_progress = CloseoutRefSerializer(many=True)
    with_open_offer = CloseoutRefSerializer(many=True)
    fingerprint = serializers.CharField()


class CloseoutSkippedSerializer(serializers.Serializer):
    application_id = serializers.UUIDField()
    reason = serializers.CharField()


class CloseoutResultSerializer(serializers.Serializer):
    notified = serializers.IntegerField()
    skipped = CloseoutSkippedSerializer(many=True)


class CandidateOfferSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    job_title = serializers.CharField()
    organisation_name = serializers.CharField()
    salary_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    period = serializers.CharField()
    start_date = serializers.DateField()
    contract_type = serializers.CharField()
    conditions = serializers.CharField(allow_blank=True)
    expires_at = serializers.DateTimeField()
    issued_at = serializers.DateTimeField(allow_null=True)
    accepted_at = serializers.DateTimeField(allow_null=True)
    declined_at = serializers.DateTimeField(allow_null=True)
    letter_document_id = serializers.UUIDField(allow_null=True)
    acceptance_statement = serializers.CharField()


def paginated(name: str, item: type[serializers.Serializer]) -> type[serializers.Serializer]:
    """``{count, next, previous, results}`` (StandardPagination) for the OpenAPI schema."""
    return type(
        name,
        (serializers.Serializer,),
        {
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": item(many=True),
        },
    )


PaginatedOfferSerializer = paginated("PaginatedOfferList", OfferSerializer)
