"""HR vacancy APIs (P03-T11, docs/04 Jobs). Thin views; logic lives in ``apps.jobs.services``.

Organisation context comes from ``X-Org-Id`` / the session (never the body). The queryset is the
caller's visible jobs (admin/HR/auditor: all of the org; recruiter/hiring manager: assigned only),
so foreign or unassigned jobs are 404.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.services import authed_user
from apps.core.exceptions import NotFoundError
from apps.core.pagination import StandardPagination
from apps.jobs import assignments as assignment_services
from apps.jobs import services, suggestions
from apps.jobs.models import Job, JobAssignment, JobEvent, JobVersion
from apps.organisations.api.views import RbacActionMixin
from apps.organisations.permissions import IsAssignedToJob
from apps.questionnaires.models import Question
from apps.questionnaires.services import record_protected_exception

from . import serializers as s


@extend_schema_view(
    list=extend_schema(
        operation_id="hr_jobs_list",
        parameters=[
            OpenApiParameter("status", str, description="Comma-separated statuses"),
            OpenApiParameter("search", str, description="Title or reference contains"),
            OpenApiParameter("assigned", str, enum=["me"], description="Only my assignments"),
            OpenApiParameter(
                "ordering", str, enum=["-updated_at", "-created_at", "closes_at", "title"]
            ),
        ],
    ),
    create=extend_schema(
        operation_id="hr_jobs_create",
        request=s.JobWriteSerializer,
        responses={201: s.HRJobDetailSerializer},
    ),
    retrieve=extend_schema(operation_id="hr_jobs_retrieve"),
    partial_update=extend_schema(
        operation_id="hr_jobs_partial_update",
        request=s.JobPatchSerializer,
        responses=s.HRJobDetailSerializer,
    ),
)
class HRJobViewSet(RbacActionMixin, viewsets.GenericViewSet):
    pagination_class = StandardPagination
    http_method_names = ["get", "post", "patch", "put"]
    read_only_actions: ClassVar[set[str]] = {"lint"}  # POST but side-effect free
    rbac_actions: ClassVar[dict[str, str]] = {
        "list": "jobs.view",
        "retrieve": "jobs.view",
        "create": "jobs.create",
        "partial_update": "jobs.create",
        "criteria": "jobs.create",
        "rubric": "jobs.create",
        "questionnaire": "jobs.create",
        "lint": "jobs.view",
        "submit_for_approval": "jobs.create",
        "approve": "jobs.approve",
        "reject": "jobs.approve",
        "publish": "jobs.publish",
        "schedule": "jobs.publish",
        "pause": "jobs.publish",
        "resume": "jobs.publish",
        "close": "jobs.publish",
        "archive": "jobs.publish",
        "extend_deadline": "jobs.publish",
        "duplicate": "jobs.create",
        "new_version": "jobs.approve",
        "ai_suggestions": "jobs.create",
        "assignments:get": "jobs.view",
        "assignments:put": "jobs.assign",
        "events": "jobs.view",
        "versions": "jobs.view",
        "protected_exception": "questions.protected_exception",
        "assisted_application": "applications.transition",
    }

    def get_permissions(self) -> list[BasePermission]:
        name = getattr(self, "action", None)
        method = (self.request.method or "").lower()
        if name and f"{name}:{method}" in self.rbac_actions:
            self.action = f"{name}:{method}"
            try:
                perms = super().get_permissions()
            finally:
                self.action = name
        else:
            perms = super().get_permissions()
        if name not in {"list", "create"}:
            perms.append(IsAssignedToJob())
        return perms

    def get_serializer_class(self) -> Any:
        return s.HRJobListSerializer if self.action == "list" else s.HRJobDetailSerializer

    def get_queryset(self) -> QuerySet[Job]:
        if getattr(self, "swagger_fake_view", False):  # OpenAPI generation
            return Job.objects.none()
        membership = self.request.membership  # type: ignore[attr-defined]
        qs = assignment_services.jobs_visible_to(membership).select_related(
            "current_version", "published_version"
        )
        if self.action != "list":
            return qs
        p = self.request.query_params
        statuses = [v for v in p.get("status", "").split(",") if v]
        if statuses:
            qs = qs.filter(status__in=statuses)
        search = p.get("search", "").strip()
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(reference_code__icontains=search))
        if p.get("assigned") == "me":
            qs = qs.filter(assignments__membership=membership).distinct()
        ordering = p.get("ordering", "-updated_at")
        if ordering not in {"-updated_at", "-created_at", "closes_at", "title"}:
            ordering = "-updated_at"
        return qs.prefetch_related("locations").order_by(ordering, "pk")

    def _job(self) -> Job:
        job: Job = self.get_object()
        return job

    def _detail(self, job: Job, code: int = status.HTTP_200_OK) -> Response:
        job = self.get_queryset().get(pk=job.pk)
        return Response(s.HRJobDetailSerializer(job).data, status=code)

    def _input(self, serializer_cls: Any) -> dict[str, Any]:
        ser = serializer_cls(data=self.request.data)
        ser.is_valid(raise_exception=True)
        data: dict[str, Any] = dict(ser.validated_data)
        return data

    # ------------------------------------------------------------------------------ CRUD
    def list(self, request: Request) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(s.HRJobListSerializer(page, many=True).data)

    def create(self, request: Request) -> Response:
        data = self._input(s.JobWriteSerializer)
        job = services.create_job(request.organisation, actor=authed_user(request), data=data)  # type: ignore[attr-defined]
        return self._detail(job, status.HTTP_201_CREATED)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        return Response(s.HRJobDetailSerializer(self._job()).data)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.JobPatchSerializer)
        lock = data.pop("lock_version")
        job = services.update_job(
            self._job(), actor=authed_user(request), data=data, lock_version=lock
        )
        return self._detail(job)

    # ------------------------------------------------------------------ authoring (PUT)
    @extend_schema(
        operation_id="hr_jobs_criteria",
        request=s.CriteriaInputSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["put"])
    def criteria(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.CriteriaInputSerializer)
        job = self._job()
        services.set_criteria(
            job,
            actor=authed_user(request),
            criteria=[dict(c) for c in data["criteria"]],
            lock_version=data.get("lock_version"),
        )
        return self._detail(job)

    @extend_schema(
        operation_id="hr_jobs_rubric",
        request=s.RubricInputSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["put"])
    def rubric(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.RubricInputSerializer)
        job = self._job()
        categories = [
            {**dict(c), "bands": [dict(b) for b in c["bands"]]} for c in data["categories"]
        ]
        services.set_rubric(
            job,
            actor=authed_user(request),
            categories=categories,
            lock_version=data.get("lock_version"),
        )
        return self._detail(job)

    @extend_schema(
        operation_id="hr_jobs_questionnaire",
        request=s.QuestionnaireInputSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["put"])
    def questionnaire(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.QuestionnaireInputSerializer)
        job = self._job()
        questions = [
            {
                **dict(q),
                "options": [dict(o) for o in q.get("options", [])],
                "criterion_id": str(q["criterion_id"]) if q.get("criterion_id") else None,
            }
            for q in data["questions"]
        ]
        services.set_questionnaire(
            job,
            actor=authed_user(request),
            questions=questions,
            lock_version=data.get("lock_version"),
        )
        return self._detail(job)

    @extend_schema(
        operation_id="hr_jobs_lint",
        request=None,
        parameters=[OpenApiParameter("stage", str, enum=["submit", "publish"])],
        responses=s.ReadinessSerializer,
    )
    @action(detail=True, methods=["post"])
    def lint(self, request: Request, pk: str | None = None) -> Response:
        stage = request.query_params.get("stage", "publish")
        result = services.readiness(self._job(), stage="submit" if stage == "submit" else "publish")
        return Response(s.ReadinessSerializer(result).data)

    @extend_schema(
        operation_id="hr_jobs_ai_suggestions", request=None, responses=s.SuggestionsSerializer
    )
    @action(detail=True, methods=["post"], url_path="ai-suggestions")
    def ai_suggestions(self, request: Request, pk: str | None = None) -> Response:
        return Response(s.SuggestionsSerializer(suggestions.suggest(self._job())).data)

    @extend_schema(
        operation_id="hr_jobs_protected_exception",
        request=s.ProtectedExceptionSerializer,
        responses=s.QuestionOutSerializer,
    )
    @action(
        detail=True,
        methods=["post"],
        url_path=r"questions/(?P<key>[a-z0-9][a-z0-9_-]{0,59})/protected-exception",
    )
    def protected_exception(
        self, request: Request, pk: str | None = None, key: str = ""
    ) -> Response:
        data = self._input(s.ProtectedExceptionSerializer)
        job = self._job()
        question = (
            Question.objects.for_org(job.organisation_id)
            .filter(questionnaire__job_version=job.current_version, key=key)
            .first()
        )
        if question is None:
            raise NotFoundError()
        question = record_protected_exception(
            question, actor=authed_user(request), reason=data["reason"]
        )
        return Response(s.question_out(question))

    # --------------------------------------------------------------------- lifecycle
    def _transition(self, fn: Any, serializer_cls: Any = None, **kwargs: Any) -> Response:
        data = self._input(serializer_cls) if serializer_cls else {}
        job = fn(self._job(), actor=authed_user(self.request), **{**data, **kwargs})
        return self._detail(job if isinstance(job, Job) else self._job())

    @extend_schema(
        operation_id="hr_jobs_submit",
        request=s.CommentSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["post"], url_path="submit-for-approval")
    def submit_for_approval(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.CommentSerializer)
        job = services.submit_for_approval(
            self._job(), actor=authed_user(request), note=data.get("comment", "")
        )
        return self._detail(job)

    @extend_schema(
        operation_id="hr_jobs_approve",
        request=s.CommentSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.approve, s.CommentSerializer)

    @extend_schema(
        operation_id="hr_jobs_reject", request=s.ReasonSerializer, responses=s.HRJobDetailSerializer
    )
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.ReasonSerializer)
        job = services.reject(
            self._job(), actor=authed_user(request), reason=data.get("reason", "")
        )
        return self._detail(job)

    @extend_schema(operation_id="hr_jobs_publish", request=None, responses=s.HRJobDetailSerializer)
    @action(detail=True, methods=["post"])
    def publish(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.publish)

    @extend_schema(
        operation_id="hr_jobs_schedule",
        request=s.ScheduleSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def schedule(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.schedule, s.ScheduleSerializer)

    @extend_schema(
        operation_id="hr_jobs_pause", request=s.ReasonSerializer, responses=s.HRJobDetailSerializer
    )
    @action(detail=True, methods=["post"])
    def pause(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.pause, s.ReasonSerializer)

    @extend_schema(operation_id="hr_jobs_resume", request=None, responses=s.HRJobDetailSerializer)
    @action(detail=True, methods=["post"])
    def resume(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.resume)

    @extend_schema(
        operation_id="hr_jobs_close", request=s.ReasonSerializer, responses=s.HRJobDetailSerializer
    )
    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.ReasonSerializer)
        job = services.close(self._job(), actor=authed_user(request), reason=data.get("reason", ""))
        return self._detail(job)

    @extend_schema(
        operation_id="hr_jobs_archive",
        request=s.ReasonSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def archive(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.archive, s.ReasonSerializer)

    @extend_schema(
        operation_id="hr_jobs_extend_deadline",
        request=s.ExtendSerializer,
        responses=s.HRJobDetailSerializer,
    )
    @action(detail=True, methods=["post"], url_path="extend-deadline")
    def extend_deadline(self, request: Request, pk: str | None = None) -> Response:
        return self._transition(services.extend_deadline, s.ExtendSerializer)

    @extend_schema(
        operation_id="hr_jobs_duplicate",
        request=s.DuplicateSerializer,
        responses={201: s.HRJobDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.DuplicateSerializer)
        copy = services.duplicate(self._job(), actor=authed_user(request), title=data.get("title"))
        return self._detail(copy, status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="hr_jobs_new_version",
        request=s.ReasonSerializer,
        responses={201: s.HRJobDetailSerializer},
    )
    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request: Request, pk: str | None = None) -> Response:
        data = self._input(s.ReasonSerializer)
        job = self._job()
        services.new_version(job, actor=authed_user(request), reason=data.get("reason", ""))
        return self._detail(job, status.HTTP_201_CREATED)

    # ------------------------------------------------------------------- related lists
    @extend_schema(
        methods=["GET"],
        operation_id="hr_jobs_assignments",
        responses=s.AssignmentSerializer(many=True),
    )
    @extend_schema(
        methods=["PUT"],
        operation_id="hr_jobs_assignments_update",
        request=s.AssignmentsInputSerializer,
        responses=s.AssignmentSerializer(many=True),
    )
    @action(detail=True, methods=["get", "put"])
    def assignments(self, request: Request, pk: str | None = None) -> Response:
        job = self._job()
        if request.method == "PUT":
            data = self._input(s.AssignmentsInputSerializer)
            rows = assignment_services.set_assignments(
                job,
                actor=authed_user(request),
                assignments=[
                    {"membership_id": str(a["membership_id"]), "role_on_job": a["role_on_job"]}
                    for a in data["assignments"]
                ],
            )
        else:
            rows = list(
                JobAssignment.objects.for_org(job.organisation_id)
                .filter(job=job)
                .select_related("membership__user")
            )
        return Response(s.AssignmentSerializer(rows, many=True).data)

    @extend_schema(operation_id="hr_jobs_events", responses=s.JobEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def events(self, request: Request, pk: str | None = None) -> Response:
        job = self._job()
        rows = JobEvent.objects.for_org(job.organisation_id).filter(job=job).order_by("created_at")
        return Response(s.JobEventSerializer(rows, many=True).data)

    @extend_schema(operation_id="hr_jobs_versions", responses=s.VersionSummarySerializer(many=True))
    @action(detail=True, methods=["get"])
    def versions(self, request: Request, pk: str | None = None) -> Response:
        job = self._job()
        rows = JobVersion.objects.for_org(job.organisation_id).filter(job=job).order_by("-number")
        return Response(s.VersionSummarySerializer(rows, many=True).data)

    # ----------------------------------------------------------- assisted application
    @extend_schema(
        operation_id="hr_jobs_assisted_application",
        request={
            "multipart/form-data": s.AssistedApplicationSerializer,
            "application/json": s.AssistedApplicationSerializer,
        },
        responses={201: s.AssistedApplicationResultSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="assisted-applications",
        parser_classes=[MultiPartParser, JSONParser],
    )
    def assisted_application(self, request: Request, pk: str | None = None) -> Response:
        """FR-M07-08 / EC-APP-17: staff submits on a candidate's behalf (flagged, consented)."""
        import json

        from apps.applications.assisted import create_assisted_application

        ser = s.AssistedApplicationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        answers = d.get("answers") or []
        if isinstance(answers, str):
            try:
                answers = json.loads(answers)
            except ValueError:
                answers = None
        if not isinstance(answers, list):
            from apps.core.exceptions import DomainError

            raise DomainError(
                "validation_error", "Invalid answers.", details={"answers": ["Invalid."]}
            )
        app = create_assisted_application(
            authed_user(request),
            self._job(),
            email=d["email"],
            first_name=d["first_name"],
            last_name=d["last_name"],
            phone=d.get("phone", ""),
            consent_confirmed=d["consent_confirmed"],
            consent_method=d["consent_method"],
            note=d.get("note", ""),
            cv=d.get("cv"),
            answers=answers,
            ip=request.META.get("REMOTE_ADDR"),
        )
        body = {
            "id": app.pk,
            "reference": app.reference,
            "status": app.status,
            "candidate_email": app.candidate_user.email,
        }
        return Response(
            s.AssistedApplicationResultSerializer(body).data, status=status.HTTP_201_CREATED
        )
