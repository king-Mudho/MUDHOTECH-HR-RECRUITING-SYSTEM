from .base import *

DEBUG = env.bool("DEBUG", default=True)
TENANT_STRICT_MODE = env.bool("TENANT_STRICT_MODE", default=True)
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# The clamav container is optional locally (compose profile "clamav"); without it scans are skipped.
DOCUMENT_SCANNER = env("DOCUMENT_SCANNER", default="skip")
