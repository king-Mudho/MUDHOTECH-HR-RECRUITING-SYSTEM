"""Deny-by-default guard: every DRF view must declare its permissions explicitly (Phase 02 exit)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.views import APIView

FRAMEWORK_BASES = {
    "APIView",
    "GenericAPIView",
    "ViewSetMixin",
    "GenericViewSet",
    "ViewSet",
    "ModelViewSet",
    "ReadOnlyModelViewSet",
}
ALLOWED_THIRD_PARTY = ("drf_spectacular.",)


def iter_views(patterns: Any = None, prefix: str = "") -> Iterator[tuple[str, Any]]:
    for p in patterns if patterns is not None else get_resolver().url_patterns:
        if isinstance(p, URLResolver):
            yield from iter_views(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            cls = getattr(p.callback, "cls", None) or getattr(p.callback, "view_class", None)
            if cls is not None and isinstance(cls, type) and issubclass(cls, APIView):
                yield prefix + str(p.pattern), cls


def declares_permissions(cls: type) -> bool:
    for klass in cls.__mro__:
        if klass.__name__ in FRAMEWORK_BASES or klass.__module__.startswith("rest_framework."):
            continue
        if "permission_classes" in vars(klass) or "get_permissions" in vars(klass):
            return True
    return False


def test_every_api_view_declares_permissions() -> None:
    views = list(iter_views())
    assert len(views) > 15  # sanity: the walker found the API
    missing = sorted(
        {
            f"{path} -> {cls.__module__}.{cls.__name__}"
            for path, cls in views
            if not cls.__module__.startswith(ALLOWED_THIRD_PARTY) and not declares_permissions(cls)
        }
    )
    assert missing == [], "Views relying on DEFAULT_PERMISSION_CLASSES:\n" + "\n".join(missing)


def test_function_views_declare_permissions() -> None:
    # @api_view functions become WrappedAPIView classes with permission_classes set by the
    # @permission_classes decorator - verify they did not rely on the default.
    from rest_framework.settings import api_settings

    for path, cls in iter_views():
        if cls.__name__ == "WrappedAPIView":
            assert cls.permission_classes is not api_settings.DEFAULT_PERMISSION_CLASSES, path
