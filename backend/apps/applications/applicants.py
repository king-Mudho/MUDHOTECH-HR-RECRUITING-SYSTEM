"""Applicants table query (P08-T05, FR-M12-01, EC-JOB-17).

Filters: status, band, score range, coverage below, flags, essentials state, tag, assigned,
search; ordering by score / coverage / submission. Pagination is by cursor (stable for 5,000+
applicants) with a total count. Every filter is a column on ``applications`` with an index, so the
database never reads evaluations for the list. In blind review, search matches the reference only:
searching by name would reveal who is behind an alias.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import F, Q, QuerySet, Value
from django.db.models.functions import Coalesce
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from apps.core.exceptions import NotFoundError
from apps.jobs.assignments import jobs_visible_to
from apps.organisations.models import Membership

from .models import Application

ORDERINGS = {
    "-score": ("-score_sort", "-submitted_at", "-id"),
    "score": ("score_asc", "submitted_at", "id"),  # unscored last in both directions
    "-submitted_at": ("-submitted_at", "-id"),
    "submitted_at": ("submitted_at", "id"),
    "coverage": ("coverage_sort", "-submitted_at", "-id"),
}
ESSENTIALS = {"all_met", "unknown", "not_evidenced"}


def _decimal(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw)) if raw not in (None, "") else None
    except InvalidOperation:
        return None


def applicants(
    membership: Membership, job_id: Any, params: dict[str, Any], *, blind: bool
) -> QuerySet[Application]:
    from .hr import applications_visible_to

    if not jobs_visible_to(membership).filter(pk=job_id).exists():
        raise NotFoundError()
    qs = applications_visible_to(membership).filter(job_id=job_id)
    split = lambda key: [v for v in str(params.get(key) or "").split(",") if v]  # noqa: E731
    if statuses := split("status"):
        qs = qs.filter(status__in=statuses)
    if bands := split("band"):
        qs = qs.filter(ai_band__in=bands)
    if (low := _decimal(params.get("min_score"))) is not None:
        qs = qs.filter(score__gte=low)
    if (high := _decimal(params.get("max_score"))) is not None:
        qs = qs.filter(score__lte=high)
    if (cov := _decimal(params.get("coverage_lt"))) is not None:
        qs = qs.filter(coverage__lt=cov)
    if flags := split("flags"):
        qs = qs.filter(flags__overlap=flags)
    essentials = params.get("essentials")
    if essentials in ESSENTIALS:
        if essentials == "all_met":
            qs = qs.filter(essentials_unknown=0, essentials_not_evidenced=0)
        elif essentials == "unknown":
            qs = qs.filter(essentials_unknown__gt=0)
        else:
            qs = qs.filter(essentials_not_evidenced__gt=0)
    if tag := str(params.get("tag") or "").strip().lower()[:40]:
        qs = qs.filter(tags__contains=[tag])
    assigned = params.get("assigned")
    if assigned == "me":
        qs = qs.filter(assigned_recruiter=membership.user_id)
    elif assigned == "none":
        qs = qs.filter(assigned_recruiter__isnull=True)
    search = str(params.get("search") or "").strip()[:100]
    if search:
        query = Q(reference__icontains=search)
        if not blind:
            snap = "candidate_profile_snapshot__"
            query |= (
                Q(**{f"{snap}first_name__icontains": search})
                | Q(**{f"{snap}last_name__icontains": search})
                | Q(**{f"{snap}email__icontains": search})
            )
        qs = qs.filter(query)
    return qs.annotate(
        score_sort=Coalesce(F("score"), Value(Decimal("-1"))),
        score_asc=Coalesce(F("score"), Value(Decimal("1000"))),
        coverage_sort=Coalesce(F("coverage"), Value(Decimal("2"))),
    ).select_related("assigned_recruiter")


class ApplicantPagination(CursorPagination):
    """Cursor pagination with the ordering chosen by the client (whitelisted) and a count."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = ORDERINGS["-score"]

    def get_ordering(self, request: Any, queryset: Any, view: Any) -> tuple[str, ...]:
        return ORDERINGS.get(request.query_params.get("ordering") or "-score", ORDERINGS["-score"])

    def paginate_queryset(self, queryset: Any, request: Any, view: Any = None) -> Any:
        self.count = queryset.count()
        return super().paginate_queryset(queryset, request, view)

    def _cursor(self, url: str | None) -> str | None:
        if not url:
            return None
        from urllib.parse import parse_qs, urlparse

        values = parse_qs(urlparse(url).query).get(self.cursor_query_param)
        return values[0] if values else None

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {
                "count": self.count,
                "next_cursor": self._cursor(self.get_next_link()),
                "previous_cursor": self._cursor(self.get_previous_link()),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["count", "results"],
            "properties": {
                "count": {"type": "integer"},
                "next_cursor": {"type": "string", "nullable": True},
                "previous_cursor": {"type": "string", "nullable": True},
                "results": schema,
            },
        }
