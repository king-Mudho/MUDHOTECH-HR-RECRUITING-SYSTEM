from .base import *

DEBUG = False
INSTALLED_APPS = [*INSTALLED_APPS, "tests.core_testapp"]
TENANT_STRICT_MODE = True
SECRET_KEY = "test-secret-key-not-for-production"  # nosec B105 - test settings only
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
OUTBOX_EAGER_PUBLISH = True
DOCUMENT_SCANNER = "fake"
# allauth rate limits use the cache; keep them generous unless a test overrides them.
# Deterministic Fernet keys used ONLY by the test-suite.
FIELD_ENCRYPTION_KEYS = (
    "k2:Mz9sV0pZQ3JhQnB5d1hGc3V6b0pVVVdoT2l6a2Q4S2s=,"
    "k1:VGhpc0lzQVRlc3RLZXlGb3JNSFJTT25seTEyMzQ1Njc="
)
S3_ENDPOINT_URL = None
S3_ACCESS_KEY = "testing"
S3_SECRET_KEY = "testing"  # nosec B105 - moto (in-memory S3) in tests
S3_REGION = "us-east-1"
LOGGING["root"]["level"] = "WARNING"  # type: ignore[index]
