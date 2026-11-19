"""Offer and hiring endpoints (P12-T06, docs/04). Staff endpoints take the organisation from
``X-Org-Id``; every lookup goes through the applications the person can see (404 otherwise).

Reading ``offers.view``; drafting, submitting, issuing ``offers.manage``; approving, returning and
withdrawing ``offers.approve``; recording a hire ``hires.record``; vacancy close-out
``applications.decide``. Issuing and confirming a close-out need an ``Idempotency-Key``.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.applications.hr import applications_visible_to
from apps.audit import services as audit
from apps.core import storage
from apps.core.exceptions import DomainError, NotFoundError
from apps.core.idempotency import idempotent
from apps.organisations.models import Membership
from apps.organisations.permissions import HasOrgAction

from .. import hiring, services
from ..models import HireRecord, Offer
from . import serializers as s


def _person(user: Any) -> str | None:
    return None if user is None else str(user.full_name or user.email)


def offer_body(o: Offer) -> dict[str, Any]:
    app = o.application
    return {
        "id": o.pk,
        "application_id": app.pk,
        "reference": app.reference,
        "job_id": app.job_id,
        "job_title": app.job.title,
        "status": o.status,
        "salary_amount": o.salary_amount,
        "currency": o.currency,
        "period": o.period,
        "start_date": o.start_date,
        "contract_type": o.contract_type,
        "conditions": o.conditions,
        "expires_at": o.expires_at,
        "required_approvals": o.required_approvals,
        "approval_round": o.approval_round,
        "approvals": [
            {
                "approver": _person(a.approver),
                "round": a.round,
                "decision": a.decision,
                "comment": a.comment,
                "at": a.at,
            }
            for a in o.approvals.select_related("approver").order_by("at")
        ],
        "created_by": _person(o.created_by),
        "issued_at": o.issued_at,
        "accepted_at": o.accepted_at,
        "counter_offer_note": o.counter_offer_note,
        "declined_at": o.declined_at,
        "decline_reason": o.decline_reason,
        "closed_at": o.closed_at,
        "close_reason": o.close_reason,
        "has_letter": o.letter_document_id is not None,
        "hire_recorded": HireRecord.objects.for_org(o.organisation_id)
        .filter(offer=o, cancelled_at__isnull=True)
        .exists(),
        "lock_version": o.lock_version,
        "openings": services.openings(app.job),
    }


def visible_offers(membership: Membership) -> QuerySet[Offer]:
    return (
        Offer.objects.for_org(membership.organisation_id)
        .filter(application__in=applications_visible_to(membership).values("pk"))
        .select_related("application__job", "created_by")
    )


def _offer(membership: Membership, offer_id: Any) -> Offer:
    o = visible_offers(membership).filter(pk=offer_id).first()
    if o is None:
        raise NotFoundError()
    return o


def _ok(o: Offer) -> Response:
    o = Offer.objects.for_org(o.organisation_id).select_related("application__job").get(pk=o.pk)
    return Response(s.OfferSerializer(offer_body(o)).data)


# --- staff ----------------------------------------------------------------------------------------
class OfferListView(APIView):
    permission_classes = [HasOrgAction("offers.view")]

    @extend_schema(
        operation_id="hr_offers",
        parameters=[OpenApiParameter("job", str), OpenApiParameter("status", str)],
        responses=s.PaginatedOfferSerializer,
    )
    def get(self, request: Request) -> Response:
        from apps.core.pagination import StandardPagination

        qs = visible_offers(request.membership)  # type: ignore[attr-defined]
        p = request.query_params
        if p.get("job"):
            qs = qs.filter(application__job_id=p["job"])
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        pager = StandardPagination()
        page = pager.paginate_queryset(qs.order_by("-created_at"), request, view=self)
        rows = [offer_body(o) for o in page or []]
        return pager.get_paginated_response(s.OfferSerializer(rows, many=True).data)


class ApplicationOffersView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "offers.view" if self.request.method == "GET" else "offers.manage"
        return [HasOrgAction(action)()]

    def _app(self, request: Request, application_id: str) -> Any:
        from apps.applications.conflicts import guard_own

        membership = request.membership  # type: ignore[attr-defined]
        guard_own(membership, application_id)
        app = applications_visible_to(membership).filter(pk=application_id).first()
        if app is None:
            raise NotFoundError()
        return app

    @extend_schema(operation_id="hr_application_offers", responses=s.OfferSerializer(many=True))
    def get(self, request: Request, application_id: str) -> Response:
        app = self._app(request, application_id)
        rows = (
            Offer.objects.for_org(app.organisation_id)
            .filter(application=app)
            .order_by("-created_at")
        )
        return Response(s.OfferSerializer([offer_body(o) for o in rows], many=True).data)

    @extend_schema(
        operation_id="hr_application_offer_create",
        request=s.OfferTermsSerializer,
        responses={201: s.OfferSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        app = self._app(request, application_id)
        data = s.OfferTermsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        o = services.create_draft(app, actor=authed_user(request), data=dict(data.validated_data))
        response = _ok(o)
        response.status_code = 201
        return response


class OfferView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "offers.view" if self.request.method == "GET" else "offers.manage"
        return [HasOrgAction(action)()]

    @extend_schema(operation_id="hr_offer", responses=s.OfferSerializer)
    def get(self, request: Request, offer_id: str) -> Response:
        return _ok(_offer(request.membership, offer_id))  # type: ignore[attr-defined]

    @extend_schema(
        operation_id="hr_offer_update", request=s.OfferPatchSerializer, responses=s.OfferSerializer
    )
    def patch(self, request: Request, offer_id: str) -> Response:
        o = _offer(request.membership, offer_id)  # type: ignore[attr-defined]
        data = s.OfferPatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = dict(data.validated_data)
        lock = v.pop("lock_version")
        return _ok(services.update_draft(o, actor=authed_user(request), data=v, lock_version=lock))


def _action(
    name: str, action: str, request_ser: Any, call: Any, *, idem: bool = False
) -> type[APIView]:
    def post(self: APIView, request: Request, offer_id: str) -> Response:
        o = _offer(request.membership, offer_id)  # type: ignore[attr-defined]
        payload: dict[str, Any] = {}
        if request_ser is not None:
            ser = request_ser(data=request.data)
            ser.is_valid(raise_exception=True)
            payload = dict(ser.validated_data)
        return _ok(call(o, authed_user(request), payload))

    post = extend_schema(
        operation_id=f"hr_offer_{name}", request=request_ser, responses=s.OfferSerializer
    )(post)
    if idem:
        post = idempotent(endpoint=f"offers.{name}")(post)
    return type(
        f"Offer{name.title()}View",
        (APIView,),
        {"permission_classes": [HasOrgAction(action)], "post": post},
    )


OfferSubmitView = _action(
    "submit", "offers.manage", None, lambda o, u, p: services.submit_for_approval(o, actor=u)
)
OfferApproveView = _action(
    "approve",
    "offers.approve",
    s.OfferCommentSerializer,
    lambda o, u, p: services.approve(o, actor=u, comment=p["comment"]),
)
OfferReturnView = _action(
    "return",
    "offers.approve",
    s.OfferRequiredCommentSerializer,
    lambda o, u, p: services.return_for_changes(o, actor=u, comment=p["comment"]),
)
OfferIssueView = _action(
    "issue", "offers.manage", None, lambda o, u, p: services.issue(o, actor=u), idem=True
)
OfferWithdrawView = _action(
    "withdraw",
    "offers.approve",
    s.OfferReasonSerializer,
    lambda o, u, p: services.withdraw(o, actor=u, reason=p["reason"]),
)


class OfferLetterView(APIView):
    """The issued letter as a PDF, streamed through the API (same origin: no bucket CORS needed)."""

    permission_classes = [HasOrgAction("offers.view")]

    @extend_schema(
        operation_id="hr_offer_letter",
        responses={(200, "application/pdf"): OpenApiResponse(description="Offer letter PDF")},
    )
    def get(self, request: Request, offer_id: str) -> HttpResponse:
        o = _offer(request.membership, offer_id)  # type: ignore[attr-defined]
        doc = o.letter_document
        if doc is None:
            raise DomainError("no_letter", "The letter is created when the offer is issued.", 409)
        audit.log_access(
            user=authed_user(request), target=doc, organisation=o.organisation_id, action="download"
        )
        response = HttpResponse(
            storage.get_bytes("documents", doc.storage_key), content_type="application/pdf"
        )
        response["Content-Disposition"] = f'attachment; filename="offer-letter-{o.pk}.pdf"'
        response["Cache-Control"] = "no-store"
        return response


class OfferHireView(APIView):
    permission_classes = [HasOrgAction("hires.record")]

    @extend_schema(
        operation_id="hr_offer_hire",
        request=s.OfferHireSerializer,
        responses={201: s.HireResultSerializer},
    )
    def post(self, request: Request, offer_id: str) -> Response:
        membership = request.membership  # type: ignore[attr-defined]
        o = _offer(membership, offer_id)
        data = s.OfferHireSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = hiring.record_hire(
            membership,
            authed_user(request),
            o.pk,
            start_date=data.validated_data["start_date"],
            note=data.validated_data["note"],
        )
        body = {
            "hire_id": result["hire"].pk,
            "start_date": result["hire"].start_date,
            "openings": result["openings"],
            "prompt_close": result["prompt_close"],
        }
        return Response(s.HireResultSerializer(body).data, status=201)


class JobCloseoutView(APIView):
    permission_classes = [HasOrgAction("applications.decide")]

    @extend_schema(operation_id="hr_job_closeout_preview", responses=s.CloseoutPreviewSerializer)
    def get(self, request: Request, job_id: str) -> Response:
        preview = hiring.closeout_preview(request.membership, job_id)  # type: ignore[attr-defined]
        return Response(s.CloseoutPreviewSerializer(preview).data)

    @extend_schema(
        operation_id="hr_job_closeout_confirm",
        request=s.CloseoutConfirmSerializer,
        responses=s.CloseoutResultSerializer,
    )
    @idempotent(endpoint="jobs.closeout")
    def post(self, request: Request, job_id: str) -> Response:
        data = s.CloseoutConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = hiring.confirm_closeout(
            request.membership,  # type: ignore[attr-defined]
            authed_user(request),
            job_id,
            **data.validated_data,
        )
        return Response(s.CloseoutResultSerializer(result).data)


# --- candidate ------------------------------------------------------------------------------------
def candidate_offer_body(o: Offer) -> dict[str, Any]:
    app = o.application
    return {
        "id": o.pk,
        "status": o.status,
        "job_title": app.job.title,
        "organisation_name": app.organisation.name,
        "salary_amount": o.salary_amount,
        "currency": o.currency,
        "period": o.period,
        "start_date": o.start_date,
        "contract_type": o.contract_type,
        "conditions": o.conditions,
        "expires_at": o.expires_at,
        "issued_at": o.issued_at,
        "accepted_at": o.accepted_at,
        "declined_at": o.declined_at,
        "letter_document_id": o.letter_document_id,
        "acceptance_statement": (
            f"I accept this offer of employment ({services.ACCEPT_STATEMENT_VERSION})"
        ),
    }


CANDIDATE_VISIBLE = ("issued", "accepted", "declined", "expired", "withdrawn")


def _own_offer(user: Any, offer_id: Any) -> Offer:
    o = (
        Offer.objects.unscoped()
        .select_related("application__job", "application__organisation")
        .filter(pk=offer_id, application__candidate_user=user, status__in=CANDIDATE_VISIBLE)
        .first()
    )
    if o is None:
        raise NotFoundError()
    return o


def _client_ip(request: Request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")


class CandidateApplicationOfferView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_application_offers", responses=s.CandidateOfferSerializer(many=True)
    )
    def get(self, request: Request, application_id: str) -> Response:
        rows = (
            Offer.objects.unscoped()
            .select_related("application__job", "application__organisation")
            .filter(
                application_id=application_id,
                application__candidate_user=authed_user(request),
                status__in=CANDIDATE_VISIBLE,
            )
            .order_by("-issued_at")
        )
        return Response(
            s.CandidateOfferSerializer([candidate_offer_body(o) for o in rows], many=True).data
        )


class CandidateAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_offer_accept",
        request=s.OfferAcceptSerializer,
        responses=s.CandidateOfferSerializer,
    )
    @idempotent(endpoint="offers.accept")
    def post(self, request: Request, offer_id: str) -> Response:
        user = authed_user(request)
        o = _own_offer(user, offer_id)
        data = s.OfferAcceptSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        done, _ = services.accept(
            o,
            candidate=user,
            typed_name=v["typed_name"],
            agree=v["agree"],
            ip=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            counter_offer_note=v["counter_offer_note"],
        )
        return Response(
            s.CandidateOfferSerializer(candidate_offer_body(_own_offer(user, done.pk))).data
        )


class CandidateDeclineView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_offer_decline",
        request=s.OfferDeclineSerializer,
        responses=s.CandidateOfferSerializer,
    )
    def post(self, request: Request, offer_id: str) -> Response:
        user = authed_user(request)
        o = _own_offer(user, offer_id)
        data = s.OfferDeclineSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.decline(o, candidate=user, reason=data.validated_data["reason"])
        return Response(
            s.CandidateOfferSerializer(candidate_offer_body(_own_offer(user, o.pk))).data
        )
