"""Pagination classes (docs/04 §1)."""

from __future__ import annotations

from typing import Any

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """`?page=&page_size=` (default 25, max 100) -> `{count, next, previous, results}`."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class StandardCursorPagination(CursorPagination):
    """For large tables (applications, audit): `{next_cursor, previous_cursor, results}`."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"

    def _cursor_value(self, url: str | None) -> str | None:
        if not url:
            return None
        from urllib.parse import parse_qs, urlparse

        values = parse_qs(urlparse(url).query).get(self.cursor_query_param)
        return values[0] if values else None

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {
                "next_cursor": self._cursor_value(self.get_next_link()),
                "previous_cursor": self._cursor_value(self.get_previous_link()),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["results"],
            "properties": {
                "next_cursor": {"type": "string", "nullable": True},
                "previous_cursor": {"type": "string", "nullable": True},
                "results": schema,
            },
        }
