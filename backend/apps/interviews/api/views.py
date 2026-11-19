"""Interview endpoints (P12-T06, docs/04). Staff endpoints take the organisation from ``X-Org-Id``.

* Arranging (create, reschedule, cancel, no-show, complete, templates): ``interviews.manage``.
* Reading an interview, its scorecards and one's own scorecard: any staff member on the panel
  or with ``interviews.view_all`` for an application they can see (otherwise 404, never 403 - the
  interview's existence is not revealed).
* Consolidated feedback: ``interviews.feedback``.
* Candidates see their own interviews, book a slot and download the calendar entry.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.applications.hr import applications_visible_to
from apps.applications.models import Application
from apps.core.exceptions import DomainError, NotFoundError
from apps.jobs.assignments import jobs_visible_to
from apps.organisations import rbac
from apps.organisations.models import Membership
from apps.organisations.permissions import HasOrgAction

from .. import scheduling, scorecards
from ..ics import interview_ics
from ..models import Interview, InterviewPanelist, InterviewSlot, Scorecard, ScorecardTemplate
from ..selectors import panel_view
from ..services import template_from_job
from . import serializers as s

PANEL_DATA = "org.view"  # any staff member; the panel / visibility check is object-level


# --- shaping --------------------------------------------------------------------------------------
def _person(user: Any) -> str:
    return str(user.full_name or user.email)


def interview_body(iv: Interview) -> dict[str, Any]:
    submitted = set(
        Scorecard.objects.for_org(iv.organisation_id)
        .filter(interview=iv, submitted_at__isnull=False)
        .values_list("panelist_id", flat=True)
    )
    app = iv.application
    return {
        "id": iv.pk,
        "application_id": app.pk,
        "reference": app.reference,
        "job_id": app.job_id,
        "job_title": app.job.title,
        "stage": iv.stage,
        "mode": iv.mode,
        "location": iv.location,
        "video_link": iv.video_link,
        "duration_minutes": iv.duration_minutes,
        "starts_at": iv.starts_at,
        "ends_at": iv.ends_at,
        "timezone": iv.timezone,
        "status": iv.status,
        "status_reason": iv.status_reason,
        "instructions": iv.instructions,
        "scorecard_template_id": iv.scorecard_template_id,
        "sequence": iv.sequence,
        "slots": [
            {"id": sl.pk, "starts_at": sl.starts_at, "ends_at": sl.ends_at, "booked": sl.booked}
            for sl in InterviewSlot.objects.for_org(iv.organisation_id).filter(interview=iv)
        ],
        "panel": [
            {
                "membership_id": p.membership_id,
                "name": _person(p.membership.user),
                "role": p.role,
                "submitted": p.pk in submitted,
            }
            for p in InterviewPanelist.objects.for_org(iv.organisation_id)
            .filter(interview=iv)
            .select_related("membership__user")
        ],
    }


def _scorecard_body(card: Scorecard, membership: Membership) -> dict[str, Any]:
    import json

    return {
        "id": card.pk,
        "panelist": _person(card.panelist.membership.user),
        "membership_id": card.panelist.membership_id,
        "own": card.panelist.membership_id == membership.pk,
        "scores": card.scores,
        "criterion_notes": json.loads(card.criterion_notes) if card.criterion_notes else {},
        "overall": card.overall,
        "recommendation": card.recommendation,
        "notes": card.notes,
        "submitted_at": card.submitted_at,
    }


# --- object access --------------------------------------------------------------------------------
def visible_interviews(membership: Membership) -> QuerySet[Interview]:
    org = membership.organisation_id
    own = (
        InterviewPanelist.objects.for_org(org).filter(membership=membership).values("interview_id")
    )
    q = Q(pk__in=own)
    if rbac.can(membership.role, "interviews.view_all"):
        q |= Q(application__in=applications_visible_to(membership).values("pk"))
    return Interview.objects.for_org(org).filter(q).select_related("application__job")


def _interview(membership: Membership, interview_id: Any, *, manage: bool = False) -> Interview:
    qs = visible_interviews(membership)
    if manage:
        qs = Interview.objects.for_org(membership.organisation_id).filter(
            application__in=applications_visible_to(membership).values("pk")
        )
    iv = qs.select_related("application__job").filter(pk=interview_id).first()
    if iv is None:
        raise NotFoundError()
    return iv


def _visible_app(membership: Membership, application_id: Any) -> Application:
    from apps.applications.conflicts import guard_own

    guard_own(membership, application_id)
    app = applications_visible_to(membership).filter(pk=application_id).first()
    if app is None:
        raise NotFoundError()
    return app


def _memberships(membership: Membership, ids: list[Any]) -> dict[str, Membership]:
    found = {
        str(m.pk): m
        for m in Membership.objects.for_org(membership.organisation_id).filter(pk__in=ids)
    }
    missing = [str(i) for i in ids if str(i) not in found]
    if missing:
        raise DomainError(
            "validation_error", "Unknown panel member.", 422, {"panel": ["Unknown member."]}
        )
    return found


def _scheduled(result: scheduling.Scheduled) -> dict[str, Any]:
    return {"interview": interview_body(result.interview), "conflicts": result.conflicts}


# --- staff views ----------------------------------------------------------------------------------
class InterviewListView(APIView):
    permission_classes = [HasOrgAction(PANEL_DATA)]

    @extend_schema(
        operation_id="hr_interviews",
        parameters=[
            OpenApiParameter("from", str, description="ISO date-time (starts_at >=)"),
            OpenApiParameter("to", str, description="ISO date-time (starts_at <)"),
            OpenApiParameter("job", str),
            OpenApiParameter("status", str),
            OpenApiParameter("mine", bool, description="only interviews I sit on"),
        ],
        responses=s.PaginatedInterviewSerializer,
    )
    def get(self, request: Request) -> Response:
        from django.utils.dateparse import parse_datetime

        from apps.core.pagination import StandardPagination

        membership: Membership = request.membership  # type: ignore[attr-defined]
        qs = visible_interviews(membership)
        p = request.query_params
        if p.get("mine") in ("1", "true"):
            qs = qs.filter(panelists__membership=membership)
        if p.get("job"):
            qs = qs.filter(application__job_id=p["job"])
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        for key, lookup in (("from", "starts_at__gte"), ("to", "starts_at__lt")):
            if p.get(key):
                when = parse_datetime(p[key])
                if when is None:
                    raise DomainError("validation_error", "Bad date.", 422, {key: ["ISO 8601."]})
                qs = qs.filter(**{lookup: when})
        pager = StandardPagination()
        page = pager.paginate_queryset(
            qs.distinct().order_by("starts_at", "created_at"), request, view=self
        )
        rows = [interview_body(iv) for iv in page or []]
        return pager.get_paginated_response(s.InterviewSerializer(rows, many=True).data)


class ApplicationInterviewsView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "interviews.view_all" if self.request.method == "GET" else "interviews.manage"
        return [HasOrgAction(action)()]

    @extend_schema(
        operation_id="hr_application_interviews", responses=s.InterviewSerializer(many=True)
    )
    def get(self, request: Request, application_id: str) -> Response:
        app = _visible_app(request.membership, application_id)  # type: ignore[attr-defined]
        rows = Interview.objects.for_org(app.organisation_id).filter(application=app)
        return Response(s.InterviewSerializer([interview_body(iv) for iv in rows], many=True).data)

    @extend_schema(
        operation_id="hr_application_interview_create",
        request=s.InterviewCreateSerializer,
        responses={201: s.ScheduledSerializer},
    )
    def post(self, request: Request, application_id: str) -> Response:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        app = _visible_app(membership, application_id)
        data = s.InterviewCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        found = _memberships(membership, [p["membership_id"] for p in v["panel"]])
        template = None
        if v["scorecard_template_id"]:
            template = (
                ScorecardTemplate.objects.for_org(membership.organisation_id)
                .filter(pk=v["scorecard_template_id"], job_id=app.job_id)
                .first()
            )
            if template is None:
                raise DomainError("validation_error", "Unknown scorecard.", 422)
        result = scheduling.create_interview(
            app,
            actor=authed_user(request),
            stage=v["stage"],
            mode=v["mode"],
            panel=[(found[str(p["membership_id"])], p["role"]) for p in v["panel"]],
            starts_at=v["starts_at"],
            slots=v["slots"],
            duration_minutes=v["duration_minutes"],
            timezone=v["timezone"],
            location=v["location"],
            video_link=v["video_link"],
            instructions=v["instructions"],
            scorecard_template=template,
        )
        return Response(s.ScheduledSerializer(_scheduled(result)).data, status=201)


class InterviewView(APIView):
    permission_classes = [HasOrgAction(PANEL_DATA)]

    @extend_schema(operation_id="hr_interview", responses=s.PanelViewSerializer)
    def get(self, request: Request, interview_id: str) -> Response:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        iv = _interview(membership, interview_id)
        view = panel_view(authed_user(request), membership, iv.pk)
        body = {
            "interview": interview_body(view["interview"]),
            "documents": view["documents"],
            "scorecard_criteria": view["scorecard_criteria"],
            "ai": view["ai"],
            "can_manage": rbac.can(membership.role, "interviews.manage"),
            "on_panel": InterviewPanelist.objects.for_org(membership.organisation_id)
            .filter(interview=iv, membership=membership)
            .exists(),
        }
        return Response(s.PanelViewSerializer(body).data)


class InterviewRescheduleView(APIView):
    permission_classes = [HasOrgAction("interviews.manage")]

    @extend_schema(
        operation_id="hr_interview_reschedule",
        request=s.RescheduleSerializer,
        responses=s.ScheduledSerializer,
    )
    def post(self, request: Request, interview_id: str) -> Response:
        iv = _interview(request.membership, interview_id, manage=True)  # type: ignore[attr-defined]
        data = s.RescheduleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        result = scheduling.reschedule(
            iv,
            actor=authed_user(request),
            reason=v["reason"],
            starts_at=v["starts_at"],
            slots=v["slots"],
        )
        return Response(s.ScheduledSerializer(_scheduled(result)).data)


class InterviewCancelView(APIView):
    permission_classes = [HasOrgAction("interviews.manage")]

    @extend_schema(
        operation_id="hr_interview_cancel",
        request=s.InterviewReasonSerializer,
        responses=s.InterviewSerializer,
    )
    def post(self, request: Request, interview_id: str) -> Response:
        iv = _interview(request.membership, interview_id, manage=True)  # type: ignore[attr-defined]
        data = s.InterviewReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = scheduling.cancel(
            iv, actor=authed_user(request), reason=data.validated_data["reason"]
        )
        return Response(s.InterviewSerializer(interview_body(done)).data)


class InterviewNoShowView(APIView):
    permission_classes = [HasOrgAction("interviews.manage")]

    @extend_schema(
        operation_id="hr_interview_no_show",
        request=s.InterviewNoteSerializer,
        responses=s.InterviewSerializer,
    )
    def post(self, request: Request, interview_id: str) -> Response:
        iv = _interview(request.membership, interview_id, manage=True)  # type: ignore[attr-defined]
        data = s.InterviewNoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = scheduling.mark_no_show(
            iv, actor=authed_user(request), note=data.validated_data["note"]
        )
        return Response(s.InterviewSerializer(interview_body(done)).data)


class InterviewCompleteView(APIView):
    permission_classes = [HasOrgAction("interviews.manage")]

    @extend_schema(
        operation_id="hr_interview_complete", request=None, responses=s.InterviewSerializer
    )
    def post(self, request: Request, interview_id: str) -> Response:
        iv = _interview(request.membership, interview_id, manage=True)  # type: ignore[attr-defined]
        done = scheduling.mark_completed(iv, actor=authed_user(request))
        return Response(s.InterviewSerializer(interview_body(done)).data)


class InterviewScorecardsView(APIView):
    permission_classes = [HasOrgAction(PANEL_DATA)]

    @extend_schema(
        operation_id="hr_interview_scorecards", responses=s.ScorecardSerializer(many=True)
    )
    def get(self, request: Request, interview_id: str) -> Response:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        iv = _interview(membership, interview_id)
        cards = scorecards.visible_scorecards(iv, membership)
        return Response(
            s.ScorecardSerializer([_scorecard_body(c, membership) for c in cards], many=True).data
        )


class MyScorecardView(APIView):
    permission_classes = [HasOrgAction(PANEL_DATA)]

    @extend_schema(
        operation_id="hr_interview_my_scorecard_save",
        request=s.ScorecardInSerializer,
        responses=s.ScorecardSerializer,
    )
    def put(self, request: Request, interview_id: str) -> Response:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        iv = _interview(membership, interview_id)
        data = s.ScorecardInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        card = scorecards.save_draft(iv, membership, dict(data.validated_data))
        return Response(s.ScorecardSerializer(_scorecard_body(card, membership)).data)


class MyScorecardSubmitView(APIView):
    permission_classes = [HasOrgAction(PANEL_DATA)]

    @extend_schema(
        operation_id="hr_interview_my_scorecard_submit",
        request=s.ScorecardInSerializer,
        responses=s.ScorecardSerializer,
    )
    def post(self, request: Request, interview_id: str) -> Response:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        iv = _interview(membership, interview_id)
        data = s.ScorecardInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        card = scorecards.submit(iv, membership, dict(data.validated_data))
        return Response(s.ScorecardSerializer(_scorecard_body(card, membership)).data)


class InterviewFeedbackView(APIView):
    permission_classes = [HasOrgAction("interviews.feedback")]

    @extend_schema(operation_id="hr_interview_feedback", responses=s.FeedbackSerializer)
    def get(self, request: Request, interview_id: str) -> Response:
        membership: Membership = request.membership  # type: ignore[attr-defined]
        iv = _interview(membership, interview_id)
        return Response(s.FeedbackSerializer(scorecards.consolidated(iv, membership)).data)


class JobScorecardTemplatesView(APIView):
    def get_permissions(self) -> list[Any]:
        action = "interviews.view_all" if self.request.method == "GET" else "interviews.manage"
        return [HasOrgAction(action)()]

    def _job(self, request: Request, job_id: str) -> Any:
        job = jobs_visible_to(request.membership).filter(pk=job_id).first()  # type: ignore[attr-defined]
        if job is None:
            raise NotFoundError()
        return job

    @staticmethod
    def _body(t: ScorecardTemplate) -> dict[str, Any]:
        return {
            "id": t.pk,
            "job_id": t.job_id,
            "name": t.name,
            "criteria": t.criteria,
            "locked": t.locked_at is not None,
        }

    @extend_schema(
        operation_id="hr_job_scorecard_templates",
        responses=s.ScorecardTemplateSerializer(many=True),
    )
    def get(self, request: Request, job_id: str) -> Response:
        job = self._job(request, job_id)
        rows = ScorecardTemplate.objects.for_org(job.organisation_id).filter(job=job)
        return Response(
            s.ScorecardTemplateSerializer([self._body(t) for t in rows], many=True).data
        )

    @extend_schema(
        operation_id="hr_job_scorecard_template_create",
        request=s.ScorecardTemplateCreateSerializer,
        responses={201: s.ScorecardTemplateSerializer},
    )
    def post(self, request: Request, job_id: str) -> Response:
        job = self._job(request, job_id)
        data = s.ScorecardTemplateCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        t = template_from_job(
            job,
            actor=authed_user(request),
            name=data.validated_data["name"],
            extra_competencies=data.validated_data["extra_competencies"],
        )
        return Response(s.ScorecardTemplateSerializer(self._body(t)).data, status=201)


# --- candidate views ------------------------------------------------------------------------------
def candidate_body(iv: Interview) -> dict[str, Any]:
    from apps.core import time as mhrs_time

    slots = []
    if iv.status == "proposed":
        slots = [
            {"id": sl.pk, "starts_at": sl.starts_at, "ends_at": sl.ends_at, "booked": sl.booked}
            for sl in InterviewSlot.objects.for_org(iv.organisation_id).filter(
                interview=iv, starts_at__gt=mhrs_time.now()
            )
        ]
    return {
        "id": iv.pk,
        "stage": iv.stage,
        "mode": iv.mode,
        "location": iv.location,
        "video_link": iv.video_link if iv.status == "scheduled" else "",
        "duration_minutes": iv.duration_minutes,
        "starts_at": iv.starts_at,
        "ends_at": iv.ends_at,
        "timezone": iv.timezone,
        "status": iv.status,
        "status_reason": iv.status_reason,
        "instructions": iv.instructions,
        "slots": slots,
    }


def _own_interview(user: Any, interview_id: Any) -> Interview:
    iv = (
        Interview.objects.unscoped()
        .select_related("application__job", "application__organisation")
        .filter(pk=interview_id, application__candidate_user=user)
        .first()
    )
    if iv is None:
        raise NotFoundError()
    return iv


class CandidateApplicationInterviewsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_application_interviews",
        responses=s.CandidateInterviewSerializer(many=True),
    )
    def get(self, request: Request, application_id: str) -> Response:
        user = authed_user(request)
        rows = (
            Interview.objects.unscoped()
            .filter(application_id=application_id, application__candidate_user=user)
            .order_by("created_at")
        )
        return Response(
            s.CandidateInterviewSerializer([candidate_body(iv) for iv in rows], many=True).data
        )


class CandidateBookView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_interview_book",
        request=s.InterviewBookSerializer,
        responses=s.CandidateInterviewSerializer,
    )
    def post(self, request: Request, interview_id: str) -> Response:
        user = authed_user(request)
        iv = _own_interview(user, interview_id)
        data = s.InterviewBookSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        done = scheduling.book_slot(iv, data.validated_data["slot_id"], candidate=user)
        return Response(s.CandidateInterviewSerializer(candidate_body(done)).data)


class CandidateCalendarView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_interview_calendar",
        responses={(200, "text/calendar"): OpenApiResponse(description="iCalendar file")},
    )
    def get(self, request: Request, interview_id: str) -> HttpResponse:
        iv = _own_interview(authed_user(request), interview_id)
        if iv.starts_at is None:
            raise DomainError("interview_not_scheduled", "Choose a time first.", 409)
        response = HttpResponse(interview_ics(iv), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="interview-{iv.pk}.ics"'
        response["Cache-Control"] = "no-store"
        return response
