"""Root URL configuration.

* ``/healthz`` / ``/readyz`` - liveness / readiness
* ``/api/v1/`` - versioned REST API (apps register their routes in ``api_v1_patterns``)
* ``/api/schema/`` + ``/api/docs/`` - OpenAPI (drf-spectacular) + Swagger UI
* ``/django-admin/`` - Django admin (internal; restricted by Nginx in production)
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.api.views import csrf
from apps.core.api.views import api_root
from apps.core.health import healthz, readyz

api_v1_patterns = [
    path("", api_root, name="api-root"),
    path("csrf/", csrf, name="csrf"),
    path("", include("apps.accounts.api.urls")),
    path("", include("apps.organisations.api.urls")),
]

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    # allauth headless (own namespaces): /api/v1/auth/browser/v1/auth/{login,signup,session,...}
    path("api/v1/auth/", include("allauth.headless.urls")),
    path("api/v1/", include((api_v1_patterns, "api"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("django-admin/", admin.site.urls),
]

handler400 = "apps.core.exceptions.json_400"
handler403 = "apps.core.exceptions.json_403"
handler404 = "apps.core.exceptions.json_404"
handler500 = "apps.core.exceptions.json_500"
