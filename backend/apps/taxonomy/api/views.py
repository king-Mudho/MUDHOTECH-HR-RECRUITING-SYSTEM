"""Taxonomy APIs (docs/04 Taxonomy)."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.audit import services as audit
from apps.core.serializers import StrictSerializer
from apps.organisations.api.views import RbacActionMixin
from apps.taxonomy import selectors, services
from apps.taxonomy.models import QualificationLevel, Skill, SkillCategory


class SkillSerializer(serializers.ModelSerializer):
    aliases = serializers.SerializerMethodField()
    is_custom = serializers.SerializerMethodField()

    class Meta:
        model = Skill
        fields = ["id", "canonical_name", "slug", "category", "aliases", "is_custom"]
        read_only_fields = fields

    def get_aliases(self, obj: Skill) -> list[str]:
        return sorted(a.alias for a in obj.aliases.all())[:8]

    def get_is_custom(self, obj: Skill) -> bool:
        return obj.organisation_id is not None


class QualificationLevelSerializer(serializers.ModelSerializer):
    aliases = serializers.SerializerMethodField()

    class Meta:
        model = QualificationLevel
        fields = ["id", "code", "name", "rank", "framework", "aliases"]
        read_only_fields = fields

    def get_aliases(self, obj: QualificationLevel) -> list[str]:
        return sorted(a.alias for a in obj.aliases.all())


class CustomSkillCreateSerializer(StrictSerializer):
    canonical_name = serializers.CharField(max_length=150)
    category = serializers.ChoiceField(choices=SkillCategory.choices)
    aliases = serializers.ListField(
        child=serializers.CharField(max_length=150), required=False, default=list, max_length=20
    )


class SkillSearchView(APIView):
    """Autocomplete for criteria builders and candidate profiles (platform + own org skills)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="taxonomy_skills_search",
        parameters=[
            OpenApiParameter("search", str, description="Text to match (names and aliases)"),
            OpenApiParameter("limit", int, description="Max results (1-50, default 20)"),
        ],
        responses=SkillSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        try:
            limit = max(1, min(50, int(request.query_params.get("limit", 20))))
        except ValueError:
            limit = 20
        skills = selectors.search_skills(
            request.query_params.get("search", ""),
            org=getattr(request, "organisation", None),
            limit=limit,
        )
        return Response(SkillSerializer(skills, many=True).data)


class QualificationLevelsView(APIView):
    """🌐 Qualification levels (ZW framework + international) with aliases."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="taxonomy_qualification_levels",
        responses=QualificationLevelSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        return Response(
            QualificationLevelSerializer(selectors.qualification_levels(), many=True).data
        )


@extend_schema_view(
    list=extend_schema(operation_id="organisations_custom_skills_list"),
    create=extend_schema(
        operation_id="organisations_custom_skills_create", request=CustomSkillCreateSerializer
    ),
    destroy=extend_schema(operation_id="organisations_custom_skills_deactivate"),
)
class CustomSkillViewSet(
    RbacActionMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Skill.objects.none()
    serializer_class = SkillSerializer
    rbac_actions: ClassVar[dict[str, str]] = {
        "list": "structure.view",
        "create": "taxonomy.manage",
        "destroy": "taxonomy.manage",
    }

    def get_queryset(self) -> QuerySet[Skill]:
        if getattr(self, "swagger_fake_view", False):
            return Skill.objects.none()
        return (
            Skill.objects.filter(organisation=self.request.organisation, is_active=True)  # type: ignore[attr-defined]
            .prefetch_related("aliases")
            .order_by("canonical_name")
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ser = CustomSkillCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        skill = services.create_custom_skill(
            org=request.organisation,  # type: ignore[attr-defined]
            actor=authed_user(request),
            name=ser.validated_data["canonical_name"],
            category=ser.validated_data["category"],
            aliases=ser.validated_data["aliases"],
            request=request,
        )
        return Response(SkillSerializer(skill).data, status=201)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        skill = self.get_object()
        skill.is_active = False  # evaluations may reference it: deactivate, never delete
        skill.save(update_fields=["is_active", "updated_at"])
        audit.record(
            actor=authed_user(request),
            action="taxonomy.custom_skill_deactivated",
            target=skill,
            organisation=skill.organisation_id,
            request=request,
        )
        return Response(status=204)
