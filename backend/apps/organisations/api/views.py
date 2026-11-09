"""Organisation & team APIs (docs/04). Views are thin; services hold the logic."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import authed_user, require_verified_email
from apps.audit import services as audit
from apps.core.viewsets import TenantScopedViewSet
from apps.organisations import services
from apps.organisations.models import Department, Invitation, Location, Membership, Organisation
from apps.organisations.permissions import HasOrgAction

from .serializers import (
    DeactivationSerializer,
    DepartmentSerializer,
    InvitationCreateSerializer,
    InvitationPublicSerializer,
    InvitationSerializer,
    LocationSerializer,
    MembershipSerializer,
    MembershipUpdateSerializer,
    OrganisationCreateSerializer,
    OrganisationSerializer,
    PolicySerializer,
    PublicCompanySerializer,
    RequiredReasonSerializer,
)


class RbacActionMixin:
    """Map each DRF action to an RBAC action in ``rbac.ORG_ACTIONS`` (deny by default)."""

    rbac_actions: ClassVar[dict[str, str]] = {}

    def get_permissions(self) -> list[BasePermission]:
        name = getattr(self, "action", None) or (self.request.method or "").lower()  # type: ignore[attr-defined]
        try:
            rbac_action = self.rbac_actions[name]
        except KeyError:
            from apps.core.exceptions import PermissionDeniedError

            raise PermissionDeniedError() from None
        return [HasOrgAction(rbac_action)()]


# ----------------------------------------------------------------------------- organisations
@extend_schema_view(
    create=extend_schema(operation_id="organisations_create", request=OrganisationCreateSerializer),
    retrieve=extend_schema(operation_id="organisations_retrieve"),
    partial_update=extend_schema(operation_id="organisations_partial_update"),
)
class OrganisationViewSet(
    RbacActionMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganisationSerializer
    lookup_url_kwarg = "organisation_id"
    http_method_names = ["get", "post", "patch"]
    rbac_actions: ClassVar[dict[str, str]] = {
        "retrieve": "org.view",
        "partial_update": "org.update",
    }

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "create":
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_object(self) -> Organisation:
        return self.request.organisation  # type: ignore[attr-defined]

    def get_queryset(self) -> QuerySet[Organisation]:  # pragma: no cover - get_object bypasses it
        return Organisation.objects.none()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = authed_user(request)
        require_verified_email(user)
        ser = OrganisationCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        org = services.create_organisation(user=user, data=ser.validated_data, request=request)
        request.membership = Membership.objects.for_org(org).get(user=user)  # type: ignore[attr-defined]
        return Response(OrganisationSerializer(org, context={"request": request}).data, status=201)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ser = OrganisationSerializer(
            self.get_object(), data=request.data, partial=True, context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        org = services.update_organisation(
            org=self.get_object(),
            actor=authed_user(request),
            data=ser.validated_data,
            request=request,
        )
        return Response(OrganisationSerializer(org, context={"request": request}).data)


class PolicyView(RbacActionMixin, APIView):
    rbac_actions: ClassVar[dict[str, str]] = {"get": "policy.view", "patch": "policy.update"}

    @extend_schema(operation_id="organisations_policies_retrieve", responses=PolicySerializer)
    def get(self, request: Request, organisation_id: str) -> Response:
        return Response(PolicySerializer(request.organisation.policy).data)  # type: ignore[attr-defined]

    @extend_schema(
        operation_id="organisations_policies_update",
        request=PolicySerializer,
        responses=PolicySerializer,
    )
    def patch(self, request: Request, organisation_id: str) -> Response:
        org = request.organisation  # type: ignore[attr-defined]
        ser = PolicySerializer(org.policy, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        lock_version = data.pop("lock_version", None)
        if lock_version is None:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"lock_version": ["This field is required."]})
        policy = services.update_policy(
            org=org,
            actor=authed_user(request),
            data=data,
            lock_version=lock_version,
            request=request,
        )
        return Response(PolicySerializer(policy).data)


# ------------------------------------------------------------------------------- structure
class _AuditedStructureViewSet(RbacActionMixin, TenantScopedViewSet):
    rbac_actions: ClassVar[dict[str, str]] = {
        "list": "structure.view",
        "retrieve": "structure.view",
        "create": "structure.manage",
        "update": "structure.manage",
        "partial_update": "structure.manage",
        "destroy": "structure.manage",
    }
    audit_noun = "structure"

    def perform_create(self, serializer: Any) -> None:
        super().perform_create(serializer)
        audit.record(
            actor=self.request.user,
            action=f"{self.audit_noun}.created",
            target=serializer.instance,
            after=serializer.data,
            request=self.request,
        )

    def perform_update(self, serializer: Any) -> None:
        before = type(serializer)(serializer.instance).data
        serializer.save()
        audit.record(
            actor=self.request.user,
            action=f"{self.audit_noun}.updated",
            target=serializer.instance,
            before=before,
            after=serializer.data,
            request=self.request,
        )

    def perform_destroy(self, instance: Any) -> None:
        audit.record(
            actor=self.request.user,
            action=f"{self.audit_noun}.deleted",
            target=instance,
            before=type(self.get_serializer())(instance).data,
            request=self.request,
        )
        instance.delete()


class DepartmentViewSet(_AuditedStructureViewSet):
    queryset = Department.objects.unscoped()
    serializer_class = DepartmentSerializer
    audit_noun = "department"


class LocationViewSet(_AuditedStructureViewSet):
    queryset = Location.objects.unscoped()
    serializer_class = LocationSerializer
    audit_noun = "location"


# --------------------------------------------------------------------------------- members
@extend_schema_view(
    list=extend_schema(operation_id="organisations_members_list"),
    partial_update=extend_schema(
        operation_id="organisations_members_update", request=MembershipUpdateSerializer
    ),
    destroy=extend_schema(
        operation_id="organisations_members_deactivate",
        request=None,
        responses=DeactivationSerializer,
    ),
)
class MemberViewSet(
    RbacActionMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Membership.objects.none()  # schema introspection; real scoping in get_queryset
    serializer_class = MembershipSerializer
    lookup_url_kwarg = "membership_id"
    http_method_names = ["get", "patch", "delete", "post"]
    rbac_actions: ClassVar[dict[str, str]] = {
        "list": "members.view",
        "partial_update": "members.manage",
        "destroy": "members.manage",
        "reset_mfa": "members.reset_mfa",
    }

    def get_queryset(self) -> QuerySet[Membership]:
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()
        return (
            Membership.objects.for_org(self.request.organisation)  # type: ignore[attr-defined]
            .select_related("user")
            .order_by("status", "user__email")
        )

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ser = MembershipUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        membership = services.change_role(
            membership=self.get_object(),
            actor=authed_user(request),
            role=ser.validated_data["role"],
            reason=ser.validated_data.get("reason", ""),
            request=request,
        )
        return Response(MembershipSerializer(membership).data)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        result = services.deactivate_member(
            membership=self.get_object(),
            actor=authed_user(request),
            reason=str(request.data.get("reason", ""))[:500],
            request=request,
        )
        return Response(DeactivationSerializer(result).data)

    @extend_schema(
        operation_id="organisations_members_reset_mfa",
        request=RequiredReasonSerializer,
        responses=OpenApiResponse(description="Authenticators removed"),
    )
    @action(detail=True, methods=["post"], url_path="reset-mfa")
    def reset_mfa(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """EC-ACC-08: admin-assisted reset after an out-of-band identity check (reason required)."""
        from apps.accounts.mfa import reset_mfa

        ser = RequiredReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        removed = reset_mfa(
            self.get_object().user, actor=authed_user(request), reason=ser.validated_data["reason"]
        )
        return Response({"authenticators_removed": removed})


# ----------------------------------------------------------------------------- invitations
@extend_schema_view(
    list=extend_schema(operation_id="organisations_invitations_list"),
    create=extend_schema(
        operation_id="organisations_invitations_create", request=InvitationCreateSerializer
    ),
    destroy=extend_schema(operation_id="organisations_invitations_revoke"),
)
class InvitationViewSet(
    RbacActionMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Invitation.objects.none()  # schema introspection; real scoping in get_queryset
    serializer_class = InvitationSerializer
    lookup_url_kwarg = "invitation_id"
    rbac_actions: ClassVar[dict[str, str]] = {
        "list": "invitations.manage",
        "create": "invitations.manage",
        "destroy": "invitations.manage",
        "resend": "invitations.manage",
    }

    def get_queryset(self) -> QuerySet[Invitation]:
        if getattr(self, "swagger_fake_view", False):
            return Invitation.objects.none()
        qs = Invitation.objects.for_org(self.request.organisation).select_related("invited_by")  # type: ignore[attr-defined]
        if self.action == "list" and self.request.query_params.get("status") == "pending":
            from apps.core import time

            qs = qs.filter(
                accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=time.now()
            )
        return qs

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ser = InvitationCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        issued = services.invite_member(
            org=request.organisation,  # type: ignore[attr-defined]
            actor=authed_user(request),
            request=request,
            **ser.validated_data,
        )
        return Response(InvitationSerializer(issued.invitation).data, status=201)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        inv = services.revoke_invitation(
            invitation=self.get_object(), actor=authed_user(request), request=request
        )
        return Response(InvitationSerializer(inv).data)

    @extend_schema(operation_id="organisations_invitations_resend", request=None)
    @action(detail=True, methods=["post"])
    def resend(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        issued = services.resend_invitation(
            invitation=self.get_object(), actor=authed_user(request), request=request
        )
        return Response(InvitationSerializer(issued.invitation).data)


class InvitationPreviewView(APIView):
    """🌐 Invitation preview before sign-in (no token echo, masked email)."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="invitations_preview", responses=InvitationPublicSerializer)
    def get(self, request: Request, token: str) -> Response:
        inv = services.get_invitation_by_token(token)
        return Response(InvitationPublicSerializer(InvitationPublicSerializer.build(inv)).data)


class InvitationAcceptView(APIView):
    """Accept an invitation as the signed-in, verified invitee (EC-ORG-04/05)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="invitations_accept", request=None, responses=MembershipSerializer)
    def post(self, request: Request, token: str) -> Response:
        membership = services.accept_invitation(
            token=token, user=authed_user(request), request=request
        )
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class CompanyView(APIView):
    """🌐 Public careers profile (FR-M02-01). Only active organisations are visible."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="companies_retrieve", responses=PublicCompanySerializer)
    def get(self, request: Request, slug: str) -> Response:
        org = Organisation.objects.filter(slug=slug, status=Organisation.Status.ACTIVE).first()
        if org is None:
            from apps.core.exceptions import NotFoundError

            raise NotFoundError()
        return Response(PublicCompanySerializer(org).data)
