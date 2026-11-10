"""Candidate profile APIs (docs/04 Candidate profile). Every query is scoped to request.user."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.candidates import services
from apps.candidates.models import (
    CandidateSkill,
    Certification,
    Education,
    Experience,
    Language,
)
from apps.core.exceptions import ConflictError

from . import serializers as s


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="candidate_profile_retrieve", responses=s.ProfileSerializer)
    def get(self, request: Request) -> Response:
        profile = services.get_or_create_profile(authed_user(request))
        return Response(s.ProfileSerializer(profile).data)

    @extend_schema(
        operation_id="candidate_profile_partial_update",
        request=s.ProfileSerializer,
        responses=s.ProfileSerializer,
    )
    def patch(self, request: Request) -> Response:
        ser = s.ProfileSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        lock = data.pop("lock_version", None)
        if "links" in data:
            data["links"] = dict(data["links"])
        profile = services.update_profile(authed_user(request), data, lock_version=lock)
        return Response(s.ProfileSerializer(profile).data)


class SectionViewSet(viewsets.ModelViewSet):
    """CRUD for one profile section; the profile always comes from the signed-in user."""

    permission_classes: ClassVar[list[Any]] = [IsAuthenticated]  # type: ignore[misc]
    model: ClassVar[Any]
    http_method_names = ["get", "post", "patch", "delete"]
    pagination_class = None

    def get_queryset(self) -> QuerySet[Any]:
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
        return self.model.objects.filter(profile__user=self.request.user)

    def _save(self, serializer: Any, **extra: Any) -> None:
        try:
            with transaction.atomic():
                serializer.save(**extra)
        except IntegrityError as exc:
            raise ConflictError(
                "conflict.duplicate", "This entry is already on your profile."
            ) from exc
        services.recompute_completeness(services.get_or_create_profile(self.request.user))

    def perform_create(self, serializer: Any) -> None:
        self._save(serializer, profile=services.get_or_create_profile(authed_user(self.request)))

    def perform_update(self, serializer: Any) -> None:
        self._save(serializer)

    def perform_destroy(self, instance: Any) -> None:
        instance.delete()
        services.recompute_completeness(services.get_or_create_profile(self.request.user))


def _section(model: Any, serializer: Any, name: str) -> type[SectionViewSet]:
    view = type(
        f"{model.__name__}ViewSet",
        (SectionViewSet,),
        {"model": model, "serializer_class": serializer},
    )
    return extend_schema_view(
        list=extend_schema(operation_id=f"candidate_{name}_list"),
        create=extend_schema(operation_id=f"candidate_{name}_create"),
        retrieve=extend_schema(operation_id=f"candidate_{name}_retrieve"),
        partial_update=extend_schema(operation_id=f"candidate_{name}_partial_update"),
        destroy=extend_schema(operation_id=f"candidate_{name}_destroy"),
    )(view)


ExperienceViewSet = _section(Experience, s.ExperienceSerializer, "experiences")
EducationViewSet = _section(Education, s.EducationSerializer, "educations")
CertificationViewSet = _section(Certification, s.CertificationSerializer, "certifications")
SkillViewSet = _section(CandidateSkill, s.CandidateSkillSerializer, "skills")
LanguageViewSet = _section(Language, s.LanguageSerializer, "languages")


# ------------------------------------------------------------------------------- CV library
class ResumeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    original_filename = serializers.CharField()
    size_bytes = serializers.IntegerField()
    page_count = serializers.IntegerField(allow_null=True)
    scan_status = serializers.CharField()
    rejected_reason = serializers.CharField()
    created_at = serializers.DateTimeField()
    is_default = serializers.BooleanField()


class ResumeListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="candidate_resumes_list", responses=ResumeSerializer(many=True))
    def get(self, request: Request) -> Response:
        from apps.candidates import resumes

        user = authed_user(request)
        default_id = services.get_or_create_profile(user).default_resume_id
        rows = [
            {
                "id": d.pk,
                "original_filename": d.original_filename,
                "size_bytes": d.size_bytes,
                "page_count": d.page_count,
                "scan_status": d.scan_status,
                "rejected_reason": d.rejected_reason,
                "created_at": d.created_at,
                "is_default": d.pk == default_id,
            }
            for d in resumes.resumes(user)[:50]
        ]
        return Response(ResumeSerializer(rows, many=True).data)


class ResumeSetDefaultView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="candidate_resumes_set_default", request=None, responses=s.ProfileSerializer
    )
    def post(self, request: Request, document_id: str) -> Response:
        from apps.candidates import resumes

        profile = resumes.set_default(authed_user(request), document_id)
        return Response(s.ProfileSerializer(profile).data)


class ResumeDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="candidate_resumes_destroy", responses={204: None})
    def delete(self, request: Request, document_id: str) -> Response:
        from apps.candidates import resumes

        resumes.remove(authed_user(request), document_id)
        return Response(status=204)
