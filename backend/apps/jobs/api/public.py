"""🌐 Public job board APIs (P03-T10): list/search, detail, questions, sitemap and feeds."""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.exceptions import DomainError, NotFoundError
from apps.core.pagination import StandardPagination
from apps.jobs import selectors
from apps.jobs.models import Job, JobStatus
from apps.jobs.search import plain_text


class GoneError(DomainError):
    code = "gone"
    status_code = status.HTTP_410_GONE
    default_message = "This vacancy is no longer available."


# ------------------------------------------------------------------------------ serializers
class PublicOrgSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)
    verified = serializers.BooleanField()


class PublicLocationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    city = serializers.CharField()


class SalarySerializer(serializers.Serializer):
    min = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    max = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    currency = serializers.CharField()
    period = serializers.CharField()


class PublicCriterionSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    min_months = serializers.IntegerField(allow_null=True)
    equivalents = serializers.ListField(child=serializers.CharField())


class PublicOptionSerializer(serializers.Serializer):
    label = serializers.CharField()  # type: ignore[assignment]
    value = serializers.CharField()


class PublicQuestionSerializer(serializers.Serializer):
    key = serializers.CharField()
    section = serializers.CharField()
    type = serializers.CharField()
    prompt = serializers.CharField()
    help_text = serializers.CharField()  # type: ignore[assignment]
    required = serializers.BooleanField()  # type: ignore[assignment]
    config = serializers.DictField()
    branching = serializers.DictField()
    options = PublicOptionSerializer(many=True)


def _org(job: Job) -> dict[str, Any]:
    from apps.organisations.logo import logo_url

    org = job.organisation
    return {
        "slug": org.slug,
        "name": org.name,
        "logo_url": logo_url(org),
        "verified": org.verified_at is not None,
    }


class PublicJobListSerializer(serializers.ModelSerializer):
    organisation = serializers.SerializerMethodField()
    locations = serializers.SerializerMethodField()
    salary = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id",
            "slug",
            "title",
            "organisation",
            "locations",
            "workplace_type",
            "employment_type",
            "seniority",
            "openings",
            "salary",
            "summary",
            "closes_at",
            "timezone",
            "published_at",
        ]
        read_only_fields = fields

    @extend_schema_field(PublicOrgSerializer)
    def get_organisation(self, obj: Job) -> dict[str, Any]:
        return _org(obj)

    @extend_schema_field(PublicLocationSerializer(many=True))
    def get_locations(self, obj: Job) -> list[dict[str, Any]]:
        return [{"id": loc.pk, "name": loc.name, "city": loc.city} for loc in obj.locations.all()]

    @extend_schema_field(SalarySerializer(allow_null=True))
    def get_salary(self, obj: Job) -> dict[str, Any] | None:
        if not obj.salary_disclosed or (obj.salary_min is None and obj.salary_max is None):
            return None
        # EC-JOB-15: shown in the advertised currency; no FX conversion is stored as fact.
        return {
            # Money is serialised as decimal strings, never floats.
            "min": str(obj.salary_min) if obj.salary_min is not None else None,
            "max": str(obj.salary_max) if obj.salary_max is not None else None,
            "currency": obj.salary_currency,
            "period": obj.salary_period,
        }

    @extend_schema_field(OpenApiTypes.STR)
    def get_summary(self, obj: Job) -> str:
        v = obj.published_version
        return (v.summary or plain_text(v.responsibilities_html))[:300] if v else ""


class PublicJobDetailSerializer(PublicJobListSerializer):
    status = serializers.CharField(read_only=True)
    is_closed = serializers.SerializerMethodField()
    accepts_applications = serializers.SerializerMethodField()
    version = serializers.SerializerMethodField()
    responsibilities_html = serializers.SerializerMethodField()
    requirements_html = serializers.SerializerMethodField()
    benefits_html = serializers.SerializerMethodField()
    required_documents = serializers.SerializerMethodField()
    essential_criteria = serializers.SerializerMethodField()
    preferred_criteria = serializers.SerializerMethodField()
    visibility = serializers.CharField(read_only=True)
    closed_at = serializers.DateTimeField(read_only=True)
    start_date = serializers.DateField(read_only=True)

    class Meta(PublicJobListSerializer.Meta):
        fields = [
            *PublicJobListSerializer.Meta.fields,
            "status",
            "visibility",
            "is_closed",
            "accepts_applications",
            "closed_at",
            "start_date",
            "version",
            "responsibilities_html",
            "requirements_html",
            "benefits_html",
            "required_documents",
            "essential_criteria",
            "preferred_criteria",
        ]
        read_only_fields = fields

    def get_is_closed(self, obj: Job) -> bool:
        return obj.status == JobStatus.CLOSED

    def get_accepts_applications(self, obj: Job) -> bool:
        from apps.core.time import now

        return obj.status == JobStatus.PUBLISHED and (
            obj.closes_at is None or obj.closes_at > now()
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_version(self, obj: Job) -> int | None:
        return obj.published_version.number if obj.published_version else None

    def _v(self, obj: Job, name: str) -> Any:
        return getattr(obj.published_version, name) if obj.published_version else ""

    def get_responsibilities_html(self, obj: Job) -> str:
        return str(self._v(obj, "responsibilities_html"))

    def get_requirements_html(self, obj: Job) -> str:
        return str(self._v(obj, "requirements_html"))

    def get_benefits_html(self, obj: Job) -> str:
        return str(self._v(obj, "benefits_html"))

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_required_documents(self, obj: Job) -> list[str]:
        return list(self._v(obj, "required_documents") or [])

    def _criteria(self, obj: Job, importance: str) -> list[dict[str, Any]]:
        if obj.published_version is None:
            return []
        # Justifications and weights are internal; candidates see the requirement itself.
        return [
            {
                "type": c.type,
                "title": c.title,
                "description": c.description,
                "min_months": c.min_months,
                "equivalents": c.equivalents,
            }
            for c in obj.published_version.criteria.all()
            if c.importance == importance
        ]

    @extend_schema_field(PublicCriterionSerializer(many=True))
    def get_essential_criteria(self, obj: Job) -> list[dict[str, Any]]:
        return self._criteria(obj, "essential")

    @extend_schema_field(PublicCriterionSerializer(many=True))
    def get_preferred_criteria(self, obj: Job) -> list[dict[str, Any]]:
        return self._criteria(obj, "preferred")


# ------------------------------------------------------------------------------------ views
class PublicJobListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicJobListSerializer
    pagination_class = StandardPagination
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_search"

    def get_queryset(self) -> Any:
        return selectors.public_jobs(self.request.query_params)

    @extend_schema(
        operation_id="jobs_public_list",
        parameters=[
            OpenApiParameter("q", str, description="Full-text search"),
            OpenApiParameter("location", str, description="Location id, city or name"),
            OpenApiParameter("workplace_type", str, description="Comma-separated"),
            OpenApiParameter("employment_type", str, description="Comma-separated"),
            OpenApiParameter("seniority", str, description="Comma-separated"),
            OpenApiParameter("org", str, description="Organisation slug"),
            OpenApiParameter("posted_within", int, description="Days"),
            OpenApiParameter("closing_within", int, description="Days"),
            OpenApiParameter("ordering", str, enum=["relevance", "newest", "closing", "title"]),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().get(request, *args, **kwargs)


def _lookup(slug_or_id: str) -> Job | Response:
    found = selectors.public_job(slug_or_id)
    if found.redirect_slug:
        return Response(
            {"redirect": found.redirect_slug},
            status=status.HTTP_301_MOVED_PERMANENTLY,
            headers={"Location": f"/api/v1/jobs/{found.redirect_slug}/"},
        )
    if found.gone:
        raise GoneError()
    if found.job is None:
        raise NotFoundError()
    return found.job


class PublicJobDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(operation_id="jobs_public_retrieve", responses=PublicJobDetailSerializer)
    def get(self, request: Request, slug: str) -> Response:
        job = _lookup(slug)
        if isinstance(job, Response):
            return job
        return Response(PublicJobDetailSerializer(job).data)


class PublicJobQuestionsView(APIView):
    """Approved questionnaire of the published version (no scoring or knock-out config)."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="jobs_public_questions", responses=PublicQuestionSerializer(many=True)
    )
    def get(self, request: Request, slug: str) -> Response:
        job = _lookup(slug)
        if isinstance(job, Response):
            return job
        if job.status == JobStatus.CLOSED or job.published_version is None:
            raise GoneError(message="This vacancy is closed.")
        data = [
            {
                "key": q.key,
                "section": q.section,
                "type": q.type,
                "prompt": q.prompt,
                "help_text": q.help_text,
                "required": q.required,
                "config": {k: v for k, v in q.config.items() if k != "knockout_expected"},
                "branching": q.branching,
                "options": [{"label": o.label, "value": o.value} for o in q.options.all()],
            }
            for q in selectors.public_questions(job)
        ]
        return Response(PublicQuestionSerializer(data, many=True).data)


def _job_url(job: Job) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/jobs/{job.slug}"


class SitemapView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="jobs_sitemap", responses={(200, "application/xml"): OpenApiTypes.STR}
    )
    def get(self, request: Request) -> HttpResponse:
        base = settings.FRONTEND_URL.rstrip("/")
        urls = [f"<url><loc>{escape(base)}/jobs</loc><changefreq>hourly</changefreq></url>"]
        orgs: set[str] = set()
        for job in selectors.sitemap_jobs():
            lastmod = job.updated_at.date().isoformat()
            urls.append(
                f"<url><loc>{escape(_job_url(job))}</loc><lastmod>{lastmod}</lastmod></url>"
            )
            orgs.add(job.organisation.slug)
        for slug in sorted(orgs):
            urls.append(f"<url><loc>{escape(base)}/companies/{escape(slug)}</loc></url>")
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls)
            + "</urlset>"
        )
        return HttpResponse(body, content_type="application/xml; charset=utf-8")


class JobsFeedView(APIView):
    """Latest 100 public vacancies as RSS 2.0 (``feed.rss``) or JSON Feed 1.1 (``feed.json``)."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="jobs_feed", responses={(200, "application/rss+xml"): OpenApiTypes.STR}
    )
    def get(self, request: Request, fmt: str) -> HttpResponse:
        jobs = list(selectors.public_jobs({"ordering": "newest"})[:100])
        base = settings.FRONTEND_URL.rstrip("/")
        if fmt == "json":
            return JsonResponse(
                {
                    "version": "https://jsonfeed.org/version/1.1",
                    "title": "MUDHOTECH HR RECRUITING SYSTEM - latest vacancies",
                    "home_page_url": f"{base}/jobs",
                    "items": [
                        {
                            "id": str(j.pk),
                            "url": _job_url(j),
                            "title": f"{j.title} - {j.organisation.name}",
                            "content_text": PublicJobListSerializer().get_summary(j),
                            "date_published": j.published_at.isoformat()
                            if j.published_at
                            else None,
                        }
                        for j in jobs
                    ],
                },
                content_type="application/feed+json",
            )
        items = "".join(
            "<item>"
            f"<title>{escape(j.title)} - {escape(j.organisation.name)}</title>"
            f"<link>{escape(_job_url(j))}</link>"
            f'<guid isPermaLink="false">{j.pk}</guid>'
            f"<description>{escape(PublicJobListSerializer().get_summary(j))}</description>"
            + (
                f"<pubDate>{j.published_at.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
                if j.published_at
                else ""
            )
            + "</item>"
            for j in jobs
        )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            "<title>MUDHOTECH HR RECRUITING SYSTEM - latest vacancies</title>"
            f"<link>{escape(base)}/jobs</link><description>Latest vacancies</description>"
            f"{items}</channel></rss>"
        )
        return HttpResponse(body, content_type="application/rss+xml; charset=utf-8")
