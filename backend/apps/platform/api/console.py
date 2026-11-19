"""Platform admin console API (P14-T01). Platform staff read; platform admins write."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user
from apps.core import deadletters
from apps.core.exceptions import NotFoundError
from apps.core.health import run_checks
from apps.core.models import DeadLetter
from apps.core.serializers import StrictSerializer
from apps.organisations.permissions import IsPlatformAdmin, IsPlatformStaff
from apps.platform import console
from apps.taxonomy import curation
from apps.taxonomy.models import QualificationLevel, SkillCategory, SkillRelation


class StaffReadAdminWrite:
    def get_permissions(self) -> list[Any]:
        method = self.request.method  # type: ignore[attr-defined]
        return [IsPlatformStaff()] if method in ("GET", "HEAD") else [IsPlatformAdmin()]


# --- serializers --------------------------------------------------------------------------------
class DayCountSerializer(serializers.Serializer):
    day = serializers.DateField()
    count = serializers.IntegerField()


class PlatformErrorsSerializer(serializers.Serializer):
    dead_letters_open = serializers.IntegerField()
    dead_letters_24h = serializers.IntegerField()
    extraction_runs_24h = serializers.IntegerField()
    extraction_failure_rate_24h = serializers.FloatField(allow_null=True)


class PlatformOverviewSerializer(serializers.Serializer):
    tenants = serializers.DictField(child=serializers.IntegerField())
    active_vacancies = serializers.IntegerField()
    applications_per_day = DayCountSerializer(many=True)
    error_rates = PlatformErrorsSerializer()
    health = serializers.DictField()


class OrgUsageSerializer(serializers.Serializer):
    active_vacancies = serializers.IntegerField()
    applications_this_month = serializers.IntegerField()
    ai_evaluations_this_month = serializers.IntegerField()
    storage_bytes = serializers.IntegerField()


class PlatformOrgDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    status = serializers.CharField()
    verified_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    members_by_role = serializers.DictField(child=serializers.IntegerField())
    usage = OrgUsageSerializer()


class PlatformUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    name = serializers.CharField(allow_blank=True)
    platform_role = serializers.CharField()
    is_active = serializers.BooleanField()
    memberships = serializers.IntegerField()
    last_login = serializers.DateTimeField(allow_null=True)


class FlagOverrideSerializer(serializers.Serializer):
    organisation_id = serializers.UUIDField()
    organisation_name = serializers.CharField(allow_blank=True)
    enabled = serializers.BooleanField()


class PlatformFlagSerializer(serializers.Serializer):
    key = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    # "global" is a Python keyword, so the field is renamed in to_representation
    global_ = serializers.BooleanField(allow_null=True)
    overrides = FlagOverrideSerializer(many=True)

    def get_fields(self) -> dict[str, serializers.Field]:
        fields = super().get_fields()
        fields["global"] = fields.pop("global_")
        return fields


class FlagSetSerializer(StrictSerializer):
    key = serializers.CharField(max_length=100)
    enabled = serializers.BooleanField()
    organisation_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class DeadLetterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeadLetter
        fields = [
            "id",
            "task_name",
            "error",
            "organisation_id",
            "request_id",
            "created_at",
            "resolved_at",
        ]


class ResolveSerializer(StrictSerializer):
    reason = serializers.CharField(min_length=5, max_length=500)


class SystemSerializer(serializers.Serializer):
    checks = serializers.DictField()
    health = serializers.DictField()


class CuratedAliasSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    alias = serializers.CharField()


class RelationOutSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    relation = serializers.CharField()
    to_skill_id = serializers.UUIDField()
    to_skill_name = serializers.CharField()


class CuratedSkillSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    canonical_name = serializers.CharField()
    category = serializers.CharField()
    is_active = serializers.BooleanField()
    taxonomy_version = serializers.CharField(allow_blank=True)
    aliases = CuratedAliasSerializer(many=True)
    relations = RelationOutSerializer(many=True)


class SkillCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=150)
    category = serializers.ChoiceField(choices=SkillCategory.choices)
    aliases = serializers.ListField(
        child=serializers.CharField(max_length=150), required=False, default=list, max_length=20
    )


class SkillUpdateSerializer(StrictSerializer):
    canonical_name = serializers.CharField(max_length=150, required=False)
    category = serializers.ChoiceField(choices=SkillCategory.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class AliasInSerializer(StrictSerializer):
    alias = serializers.CharField(max_length=150)


class RelationInSerializer(StrictSerializer):
    from_skill = serializers.UUIDField()
    to_skill = serializers.UUIDField()
    relation = serializers.ChoiceField(choices=SkillRelation.Relation.choices)


class CuratedQualificationLevelSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    rank = serializers.IntegerField()
    framework = serializers.CharField()
    aliases = CuratedAliasSerializer(many=True)


class TaxonomyVersionRowSerializer(serializers.Serializer):
    version = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    notes = serializers.CharField(allow_blank=True)


class TaxonomyStatusSerializer(serializers.Serializer):
    current_version = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)
    unpublished_changes = serializers.BooleanField()
    skills = serializers.IntegerField()
    versions = TaxonomyVersionRowSerializer(many=True)


class PublishSerializer(StrictSerializer):
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


def _skill_body(skill: Any) -> dict[str, Any]:
    return {
        "id": skill.pk,
        "canonical_name": skill.canonical_name,
        "category": skill.category,
        "is_active": skill.is_active,
        "taxonomy_version": skill.taxonomy_version,
        "aliases": [{"id": a.pk, "alias": a.alias} for a in skill.aliases.all()],
        "relations": [
            {
                "id": r.pk,
                "relation": r.relation,
                "to_skill_id": r.to_skill_id,
                "to_skill_name": r.to_skill.canonical_name,
            }
            for r in skill.relations_out.all()
        ],
    }


# --- views --------------------------------------------------------------------------------------
class PlatformOverviewView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(operation_id="platform_overview", responses=PlatformOverviewSerializer)
    def get(self, request: Request) -> Response:
        return Response(PlatformOverviewSerializer(console.overview()).data)


class PlatformOrgDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(
        operation_id="platform_organisation_detail", responses=PlatformOrgDetailSerializer
    )
    def get(self, request: Request, organisation_id: str) -> Response:
        return Response(
            PlatformOrgDetailSerializer(console.organisation_detail(organisation_id)).data
        )


class PlatformUsersView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(
        operation_id="platform_users",
        parameters=[OpenApiParameter("q", str, description="At least 3 characters")],
        responses=PlatformUserSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = console.search_users(request.query_params.get("q", "")[:100])
        return Response(PlatformUserSerializer(rows, many=True).data)


class PlatformFlagsView(StaffReadAdminWrite, APIView):
    @extend_schema(operation_id="platform_flags", responses=PlatformFlagSerializer(many=True))
    def get(self, request: Request) -> Response:
        return Response(PlatformFlagSerializer(console.list_flags(), many=True).data)

    @extend_schema(
        operation_id="platform_flag_set",
        request=FlagSetSerializer,
        responses=PlatformFlagSerializer(many=True),
    )
    def post(self, request: Request) -> Response:
        data = FlagSetSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        console.set_flag(authed_user(request), v["key"], v["enabled"], v["organisation_id"])
        return Response(PlatformFlagSerializer(console.list_flags(), many=True).data)


class PlatformDeadLettersView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(
        operation_id="platform_dead_letters",
        parameters=[OpenApiParameter("all", bool)],
        responses=DeadLetterSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = console.dead_letters(include_resolved=request.query_params.get("all") == "true")
        return Response(DeadLetterSerializer(rows, many=True).data)


class PlatformDeadLetterRetryView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_dead_letter_retry", request=None, responses=DeadLetterSerializer
    )
    def post(self, request: Request, dead_letter_id: str) -> Response:
        row = DeadLetter.objects.filter(pk=dead_letter_id).first()
        if row is None:
            raise NotFoundError()
        deadletters.retry(row, authed_user(request))
        row.refresh_from_db()
        return Response(DeadLetterSerializer(row).data)


class PlatformDeadLetterResolveView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_dead_letter_resolve",
        request=ResolveSerializer,
        responses=DeadLetterSerializer,
    )
    def post(self, request: Request, dead_letter_id: str) -> Response:
        row = DeadLetter.objects.filter(pk=dead_letter_id).first()
        if row is None:
            raise NotFoundError()
        data = ResolveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        deadletters.resolve(row, authed_user(request), data.validated_data["reason"])
        row.refresh_from_db()
        return Response(DeadLetterSerializer(row).data)


class PlatformSystemView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(operation_id="platform_system", responses=SystemSerializer)
    def get(self, request: Request) -> Response:
        return Response(
            SystemSerializer({"checks": run_checks(), "health": console.queue_health()}).data
        )


class TaxonomyStatusView(StaffReadAdminWrite, APIView):
    @extend_schema(operation_id="platform_taxonomy", responses=TaxonomyStatusSerializer)
    def get(self, request: Request) -> Response:
        return Response(TaxonomyStatusSerializer(curation.status()).data)

    @extend_schema(
        operation_id="platform_taxonomy_publish",
        request=PublishSerializer,
        responses=TaxonomyStatusSerializer,
    )
    def post(self, request: Request) -> Response:
        data = PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        curation.publish(authed_user(request), data.validated_data["notes"])
        return Response(TaxonomyStatusSerializer(curation.status()).data)


class TaxonomySkillsView(StaffReadAdminWrite, APIView):
    @extend_schema(
        operation_id="platform_taxonomy_skills",
        parameters=[OpenApiParameter("q", str), OpenApiParameter("inactive", bool)],
        responses=CuratedSkillSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        qs = curation.platform_skills(
            request.query_params.get("q", "")[:100],
            include_inactive=request.query_params.get("inactive") == "true",
        )[:100]
        return Response(CuratedSkillSerializer([_skill_body(s) for s in qs], many=True).data)

    @extend_schema(
        operation_id="platform_taxonomy_skill_create",
        request=SkillCreateSerializer,
        responses={201: CuratedSkillSerializer},
    )
    def post(self, request: Request) -> Response:
        data = SkillCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        skill = curation.create_skill(
            authed_user(request), name=v["name"], category=v["category"], aliases=v["aliases"]
        )
        return Response(CuratedSkillSerializer(_skill_body(skill)).data, status=201)


class TaxonomySkillView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_taxonomy_skill_update",
        request=SkillUpdateSerializer,
        responses=CuratedSkillSerializer,
    )
    def patch(self, request: Request, skill_id: str) -> Response:
        data = SkillUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        skill = curation.update_skill(authed_user(request), skill_id, **data.validated_data)
        return Response(CuratedSkillSerializer(_skill_body(skill)).data)


class TaxonomySkillAliasesView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_taxonomy_alias_add",
        request=AliasInSerializer,
        responses={201: CuratedAliasSerializer},
    )
    def post(self, request: Request, skill_id: str) -> Response:
        data = AliasInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = curation.add_alias(authed_user(request), skill_id, data.validated_data["alias"])
        return Response(CuratedAliasSerializer({"id": row.pk, "alias": row.alias}).data, status=201)


class TaxonomyAliasView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(operation_id="platform_taxonomy_alias_remove", responses={204: None})
    def delete(self, request: Request, alias_id: str) -> Response:
        curation.remove_alias(authed_user(request), alias_id)
        return Response(status=204)


class TaxonomyRelationsView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_taxonomy_relation_add",
        request=RelationInSerializer,
        responses={201: RelationOutSerializer},
    )
    def post(self, request: Request) -> Response:
        data = RelationInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        row = curation.add_relation(
            authed_user(request), v["from_skill"], v["to_skill"], v["relation"]
        )
        body = {
            "id": row.pk,
            "relation": row.relation,
            "to_skill_id": row.to_skill_id,
            "to_skill_name": row.to_skill.canonical_name,
        }
        return Response(RelationOutSerializer(body).data, status=201)


class TaxonomyRelationView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(operation_id="platform_taxonomy_relation_remove", responses={204: None})
    def delete(self, request: Request, relation_id: str) -> Response:
        curation.remove_relation(authed_user(request), relation_id)
        return Response(status=204)


class TaxonomyQualificationsView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(
        operation_id="platform_taxonomy_qualifications",
        responses=CuratedQualificationLevelSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        rows = [
            {
                "id": lvl.pk,
                "code": lvl.code,
                "name": lvl.name,
                "rank": lvl.rank,
                "framework": lvl.framework,
                "aliases": [{"id": a.pk, "alias": a.alias} for a in lvl.aliases.all()],
            }
            for lvl in QualificationLevel.objects.prefetch_related("aliases")
        ]
        return Response(CuratedQualificationLevelSerializer(rows, many=True).data)


class TaxonomyQualificationAliasesView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_taxonomy_qualification_alias_add",
        request=AliasInSerializer,
        responses={201: CuratedAliasSerializer},
    )
    def post(self, request: Request, level_id: str) -> Response:
        data = AliasInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = curation.add_qualification_alias(
            authed_user(request), level_id, data.validated_data["alias"]
        )
        return Response(CuratedAliasSerializer({"id": row.pk, "alias": row.alias}).data, status=201)


class TaxonomyQualificationAliasView(APIView):
    permission_classes = [IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_taxonomy_qualification_alias_remove", responses={204: None}
    )
    def delete(self, request: Request, alias_id: str) -> Response:
        curation.remove_qualification_alias(authed_user(request), alias_id)
        return Response(status=204)
