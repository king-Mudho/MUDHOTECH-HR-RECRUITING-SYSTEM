from .base import *

DEBUG = env.bool("DEBUG", default=True)
ENABLE_DJANGO_ADMIN = env.bool("ENABLE_DJANGO_ADMIN", default=True)
TENANT_STRICT_MODE = env.bool("TENANT_STRICT_MODE", default=True)
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# The clamav container is optional locally (compose profile "clamav"); without it scans are skipped.
DOCUMENT_SCANNER = env("DOCUMENT_SCANNER", default="skip")

# Load tests (P10-T05, loadtests/README.md): one Locust host stands in for many users, so the
# per-IP limits that protect production would only measure the limiter. Development settings only;
# the limiters themselves are covered by their own tests.
if env.bool("LOAD_TEST", default=False):
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = dict.fromkeys(
        REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "1000000/min"
    )
    ACCOUNT_RATE_LIMITS = False
