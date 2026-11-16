"""Shortlist endpoints (P08-T02, docs/04 Shortlisting). Org context via ``X-Org-Id``.

Reading needs ``applications.view``; proposing and deciding ``applications.transition``;
approving, returning and undoing ``applications.decide`` (dual-control rules in the service).
Approval requires an ``Idempotency-Key``.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core.idempotency import idempotent
from apps.core.serializers import StrictSerializer
from apps.organisations.permissions import HasOrgAction

from .. import services
from ..models import Shortlist, ShortlistEntry


# ------------------------------------------------------------------------------- serializers
class ShortlistProposeSerializer(StrictSerializer):
    desired_size = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=1000
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=4000)


class ShortlistDecisionSerializer(StrictSerializer):
    application_id = serializers.UUIDField()
    decision = serializers.ChoiceField(choices=ShortlistEntry.Decision.choices)
    reason_code = serializers.CharField(required=False, allow_blank=True, default="", max_length=40)
    reason_text = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=2000
    )


class ShortlistDecisionsSerializer(StrictSerializer):
    decisions = ShortlistDecisionSerializer(many=True, min_length=1, max_length=1000)  # type: ignore[call-arg]
    lock_version = serializers.IntegerField(required=False, allow_null=True, default=None)


class ShortlistLockSerializer(StrictSerializer):
    lock_version = serializers.IntegerField(required=False, allow_null=True, default=None)


class ShortlistReasonSerializer(ShortlistLockSerializer):
    reason = serializers.CharField(max_length=2000)


class ShortlistEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    application_id = serializers.UUIDField()
    reference = serializers.CharField(allow_null=True)
    candidate_name = serializers.CharField()
    identity_hidden = serializers.BooleanField()
    status = serializers.CharField()
    suggestion = serializers.CharField(allow_blank=True)
    decision = serializers.CharField()
    reason_code = serializers.CharField(allow_blank=True)
    reason_text = serializers.CharField(allow_blank=True)
    ai_band = serializers.CharField(allow_blank=True)
    score = serializers.FloatField(allow_null=True)
    coverage = serializers.FloatField(allow_null=True)
    override = serializers.BooleanField()
    decided_by = serializers.CharField(allow_null=True)
    decided_at = serializers.DateTimeField(allow_null=True)
    applied_at = serializers.DateTimeField(allow_null=True)
    apply_note = serializers.CharField(allow_blank=True)


class ShortlistSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    undecided = serializers.IntegerField()
    shortlist = serializers.IntegerField()
    not_selected = serializers.IntegerField()
    hold = serializers.IntegerField()
    overrides = serializers.IntegerField()
    low_coverage = serializers.IntegerField()
    uncertain_not_selected = serializers.IntegerField()
    reasons = serializers.DictField(child=serializers.IntegerField())
    above_desired_size = serializers.BooleanField()


class ShortlistSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    job_version_id = serializers.UUIDField()
    status = serializers.CharField()
    desired_size = serializers.IntegerField(allow_null=True)
    proposed_by = serializers.CharField()
    proposed_by_id = serializers.UUIDField()
    submitted_at = serializers.DateTimeField(allow_null=True)
    approved_at = serializers.DateTimeField(allow_null=True)
    notify_after = serializers.DateTimeField(allow_null=True)
    return_reason = serializers.CharField(allow_blank=True)
    undo_reason = serializers.CharField(allow_blank=True)
    notes = serializers.CharField(allow_blank=True)
    lock_version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    summary = ShortlistSummarySerializer()


class ShortlistDetailSerializer(ShortlistSerializer):
    entries = ShortlistEntrySerializer(many=True)


# ------------------------------------------------------------------------------- shaping
def _person(user: Any) -> str | None:
    if user is None:
        return None
    return str(user.full_name or user.email)


def _shortlist(s: Shortlist, *, entries: bool = False, user: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": s.pk,
        "job_id": s.job_id,
        "job_version_id": s.job_version_id,
        "status": s.status,
        "desired_size": s.desired_size,
        "proposed_by": _person(s.proposed_by),
        "proposed_by_id": s.proposed_by_id,
        "submitted_at": s.submitted_at,
        "approved_at": s.approved_at,
        "notify_after": s.notify_after,
        "return_reason": s.return_reason,
        "undo_reason": s.undo_reason,
        "notes": s.notes,
        "lock_version": s.lock_version,
        "created_at": s.created_at,
        "summary": services.summary(s),
    }
    if entries:
        from apps.applications.blind import BlindView

        rows = list(
            services.entries_of(s)
            .select_related("application", "decided_by")
            .order_by("-score_at_decision", "created_at")
        )
        blind = BlindView(user, s.organisation_id, [e.application_id for e in rows])
        body["entries"] = [
            {
                "id": e.pk,
                "application_id": e.application_id,
                "reference": e.application.reference,
                "candidate_name": blind.name(e.application),  # P08-T04: alias in blind mode
                "identity_hidden": blind.hidden(e.application_id),
                "status": e.application.status,
                "suggestion": e.suggestion,
                "decision": e.decision,
                "reason_code": e.reason_code,
                "reason_text": e.reason_text,
                "ai_band": e.ai_band_at_decision,
                "score": float(e.score_at_decision) if e.score_at_decision is not None else None,
                "coverage": (
                    float(e.coverage_at_decision) if e.coverage_at_decision is not None else None
                ),
                "override": e.override,
                "decided_by": _person(e.decided_by),
                "decided_at": e.decided_at,
                "applied_at": e.applied_at,
                "apply_note": e.apply_note,
            }
            for e in rows
        ]
    return body


def _detail(membership: Any, shortlist_id: Any) -> Response:
    s = services.get_shortlist(membership, shortlist_id)
    body = _shortlist(s, entries=True, user=membership.user)
    return Response(ShortlistDetailSerializer(body).data)


# ------------------------------------------------------------------------------- views
class JobShortlistsView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "applications.view" if self.request.method == "GET" else "applications.transition"
        return [HasOrgAction(action)()]

    @extend_schema(operation_id="hr_job_shortlists", responses=ShortlistSerializer(many=True))
    def get(self, request: Request, job_id: str) -> Response:
        job = services._job(request.membership, job_id)  # type: ignore[attr-defined]
        rows = Shortlist.objects.for_org(job.organisation_id).filter(job=job)[:50]
        return Response(ShortlistSerializer([_shortlist(s) for s in rows], many=True).data)

    @extend_schema(
        operation_id="hr_job_shortlist_propose",
        request=ShortlistProposeSerializer,
        responses={201: ShortlistDetailSerializer},
    )
    def post(self, request: Request, job_id: str) -> Response:
        data = ShortlistProposeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        s = services.create_proposal(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            job_id,
            desired_size=data.validated_data.get("desired_size"),
            notes=data.validated_data["notes"],
        )
        body = _shortlist(s, entries=True, user=authed_user(request))
        return Response(ShortlistDetailSerializer(body).data, status=201)


class ShortlistView(APIView):
    permission_classes = [HasOrgAction("applications.view")]

    @extend_schema(operation_id="hr_shortlist", responses=ShortlistDetailSerializer)
    def get(self, request: Request, shortlist_id: str) -> Response:
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]


class ShortlistEntriesView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_shortlist_entries",
        request=ShortlistDecisionsSerializer,
        responses=ShortlistDetailSerializer,
    )
    def patch(self, request: Request, shortlist_id: str) -> Response:
        data = ShortlistDecisionsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_decisions(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            shortlist_id,
            data.validated_data["decisions"],
            lock_version=data.validated_data["lock_version"],
        )
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]


class ShortlistRefreshView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_shortlist_refresh", request=None, responses=ShortlistDetailSerializer
    )
    def post(self, request: Request, shortlist_id: str) -> Response:
        services.refresh_entries(request.membership, authed_user(request), shortlist_id)  # type: ignore[attr-defined]
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]


class ShortlistSubmitView(APIView):
    permission_classes = [HasOrgAction("applications.transition")]

    @extend_schema(
        operation_id="hr_shortlist_submit",
        request=ShortlistLockSerializer,
        responses=ShortlistDetailSerializer,
    )
    def post(self, request: Request, shortlist_id: str) -> Response:
        data = ShortlistLockSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.submit(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            shortlist_id,
            lock_version=data.validated_data["lock_version"],
        )
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]


IDEMPOTENCY_HEADER = OpenApiParameter(
    "Idempotency-Key", str, OpenApiParameter.HEADER, required=True, description="UUID"
)


class ShortlistApproveView(APIView):
    permission_classes = [HasOrgAction("applications.decide")]

    @extend_schema(
        operation_id="hr_shortlist_approve",
        request=ShortlistLockSerializer,
        responses=ShortlistDetailSerializer,
        parameters=[IDEMPOTENCY_HEADER],
    )
    @idempotent(endpoint="shortlists.approve")
    def post(self, request: Request, shortlist_id: str) -> Response:
        data = ShortlistLockSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.approve(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            shortlist_id,
            lock_version=data.validated_data["lock_version"],
        )
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]


class ShortlistRejectView(APIView):
    """Return the proposal to its author for changes (never about a candidate)."""

    permission_classes = [HasOrgAction("applications.decide")]

    @extend_schema(
        operation_id="hr_shortlist_reject",
        request=ShortlistReasonSerializer,
        responses=ShortlistDetailSerializer,
    )
    def post(self, request: Request, shortlist_id: str) -> Response:
        data = ShortlistReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.return_for_changes(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            shortlist_id,
            reason=data.validated_data["reason"],
            lock_version=data.validated_data["lock_version"],
        )
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]


class ShortlistUndoView(APIView):
    permission_classes = [HasOrgAction("applications.decide")]

    @extend_schema(
        operation_id="hr_shortlist_undo",
        request=ShortlistReasonSerializer,
        responses=ShortlistDetailSerializer,
    )
    def post(self, request: Request, shortlist_id: str) -> Response:
        data = ShortlistReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.undo(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            shortlist_id,
            reason=data.validated_data["reason"],
            lock_version=data.validated_data["lock_version"],
        )
        return _detail(request.membership, shortlist_id)  # type: ignore[attr-defined]
