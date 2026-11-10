"""Base settings shared by every environment. Secrets come from the environment (django-environ)."""

from datetime import timedelta
from pathlib import Path

import environ
from kombu import Queue

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# docker compose injects .env; host-side runs use the localhost defaults below unless opted in.
if env.bool("DJANGO_READ_DOT_ENV", default=False):
    environ.Env.read_env(BASE_DIR.parent / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-only-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "backend"])
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"]
)
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")
APP_NAME = "MUDHOTECH HR RECRUITING SYSTEM"
# Strict tenant guard: evaluating an unscoped TenantModel queryset inside a request context raises.
TENANT_STRICT_MODE = env.bool("TENANT_STRICT_MODE", default=False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # third party
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "storages",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.usersessions",
    "allauth.headless",
    # local
    "apps.core",
    "apps.accounts",
    "apps.organisations",
    "apps.audit",
    "apps.platform",
    "apps.taxonomy",
    "apps.jobs",
    "apps.questionnaires",
    "apps.candidates",
    "apps.documents",
    "apps.applications",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "apps.core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "allauth.usersessions.middleware.UserSessionsMiddleware",
    "apps.organisations.middleware.OrganisationContextMiddleware",
    "apps.accounts.middleware.MfaEnforcementMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://mhrs:mhrs@localhost:15432/mhrs"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6380/0")
CACHE_URL = env("CACHE_URL", default="redis://localhost:6380/1")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CACHE_URL,
        "TIMEOUT": 300,
        "KEY_PREFIX": "mhrs",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
# FR-M01-06: min 10 chars + breached/common list, no composition rules.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "apps.accounts.password_validation.BreachedPasswordValidator"},
]
BREACHED_PASSWORDS_FILE = env("BREACHED_PASSWORDS_FILE", default=None)

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
DISPLAY_TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Security baseline (tightened further in prod) ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the frontend reads it to send X-CSRFToken
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
CSRF_FAILURE_VIEW = "apps.core.exceptions.csrf_failure"
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "300/min",
        "anon": "120/min",
        "auth": "10/min",
        "public_search": "60/min",
        "uploads": "30/hour",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MUDHOTECH HR RECRUITING SYSTEM API",
    "DESCRIPTION": "Multi-tenant ATS with explainable, human-controlled AI screening.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "OrganisationStatusEnum": "apps.organisations.models.Organisation.Status",
        "MembershipStatusEnum": "apps.organisations.models.Membership.Status",
        "RoleEnum": "apps.organisations.models.Role",
        "PlatformRoleEnum": "apps.accounts.models.PlatformRole",
        "WorkplaceTypeEnum": "apps.jobs.models.WorkplaceType",
        "JobStatusEnum": "apps.jobs.models.JobStatus",
        "JobVersionStatusEnum": "apps.jobs.models.VersionStatus",
    },
}

# --- Celery ---
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=None)
CELERY_RESULT_EXPIRES = 3600
CELERY_TASK_IGNORE_RESULT = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = 300
CELERY_TASK_TIME_LIMIT = 360
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = [
    Queue(name) for name in ("default", "documents", "ai", "notifications", "reports")
]
CELERY_TASK_ROUTES = {
    "apps.documents.*": {"queue": "documents"},
    "apps.resumes.*": {"queue": "documents"},
    "apps.screening.*": {"queue": "ai"},
    "apps.notifications.*": {"queue": "notifications"},
    "apps.analytics.*": {"queue": "reports"},
}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "outbox-relay": {
        "task": "apps.core.tasks.relay_outbox",
        "schedule": timedelta(seconds=2),
        "options": {"expires": 10},
    },
    "idempotency-cleanup": {
        "task": "apps.core.tasks.purge_expired_idempotency_keys",
        "schedule": timedelta(hours=1),
    },
    "jobs-publish-scheduled": {
        "task": "apps.jobs.tasks.publish_scheduled_jobs",
        "schedule": timedelta(minutes=1),
        "options": {"expires": 50},
    },
    "documents-cleanup-uploads": {
        "task": "apps.documents.tasks.cleanup_uploads",
        "schedule": timedelta(hours=1),
        "options": {"expires": 3000},
    },
    "jobs-close-expired": {
        "task": "apps.jobs.tasks.close_expired_jobs",
        "schedule": timedelta(minutes=1),
        "options": {"expires": 50},
    },
}

# --- Outbox ---
OUTBOX_RELAY_BATCH_SIZE = 100
OUTBOX_MAX_ATTEMPTS = 10

# --- Object storage (S3 / MinIO) ---
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default=None)
# Endpoint used inside presigned URLs given to browsers (e.g. http://localhost:9000 in dev).
S3_PUBLIC_ENDPOINT_URL = env("S3_PUBLIC_ENDPOINT_URL", default=None)
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default=None)
S3_SECRET_KEY = env("S3_SECRET_KEY", default=None)
S3_REGION = env("S3_REGION", default="af-south-1")
S3_BUCKETS = {
    "quarantine": env("S3_BUCKET_QUARANTINE", default="mhrs-uploads-quarantine"),
    "documents": env("S3_BUCKET_DOCUMENTS", default="mhrs-documents"),
    "exports": env("S3_BUCKET_EXPORTS", default="mhrs-exports"),
    "public": env("S3_BUCKET_PUBLIC", default="mhrs-public"),
}
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": S3_BUCKETS["public"],
            "endpoint_url": S3_ENDPOINT_URL,
            "access_key": S3_ACCESS_KEY,
            "secret_key": S3_SECRET_KEY,
            "region_name": S3_REGION,
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- Field encryption (ADR-011) ---
# Format: "k2:<fernet-key>,k1:<fernet-key>" - the first key encrypts, every key decrypts.
FIELD_ENCRYPTION_KEYS = env("FIELD_ENCRYPTION_KEYS", default="")

# --- Email ---
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="smtp://localhost:1025")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="MUDHOTECH HR RECRUITING SYSTEM <no-reply@mhrs.local>"
)

# --- ClamAV ---
CLAMAV_HOST = env("CLAMAV_HOST", default="localhost")
CLAMAV_PORT = env.int("CLAMAV_PORT", default=3310)
CLAMAV_TIMEOUT = env.int("CLAMAV_TIMEOUT", default=30)
# clamd (default) | fake (tests: EICAR only) | skip (DEBUG only: no clamav container locally)
DOCUMENT_SCANNER = env("DOCUMENT_SCANNER", default="clamd")

# --- AI ---
LLM_PROVIDER = env("LLM_PROVIDER", default="none")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="sentence-transformers/all-MiniLM-L6-v2")

# --- Health checks ---
HEALTHCHECK_TIMEOUT_SECONDS = env.float("HEALTHCHECK_TIMEOUT_SECONDS", default=2.0)

# --- Logging (structured JSON to stdout) ---
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"context": {"()": "apps.core.logging.ContextFilter"}},
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(task_id)s",
            "rename_fields": {"asctime": "ts", "levelname": "level", "name": "logger"},
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["context"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "botocore": {"level": "WARNING"},
        "urllib3": {"level": "WARNING"},
    },
}

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:  # pragma: no cover
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False, traces_sample_rate=0.05)

# --- Authentication: django-allauth headless (ADR-004, docs/02 §5.5) ---
AUTHENTICATION_BACKENDS = [
    "apps.accounts.auth_backends.LockoutAwareAuthenticationBackend",
]
ACCOUNT_ADAPTER = "apps.accounts.adapter.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
# ADR-023: verification is required before login - this is what lets signup stay enumeration-free
# (EC-ACC-02). Submit endpoints additionally call require_verified_email() (EC-ACC-03).
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_CHANGE_EMAIL = True  # new address must be verified before it replaces the old one
ACCOUNT_EMAIL_NOTIFICATIONS = True  # notice to the old address on email/password change
ACCOUNT_PREVENT_ENUMERATION = True  # EC-ACC-02 / EC-ACC-06
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[MHRS] "
ACCOUNT_PASSWORD_MIN_LENGTH = 10
ACCOUNT_RATE_LIMITS = {
    "login": "30/m/ip",
    "login_failed": "10/m/ip,10/5m/key",
    "signup": "20/m/ip",
    "confirm_email": "1/3m/key",
    "reset_password": "20/m/ip,5/m/key",
    "reset_password_from_key": "20/m/ip",
    "change_password": "5/m/user",
    "manage_email": "10/m/user",
}
PASSWORD_RESET_TIMEOUT = 60 * 60  # single-use reset tokens valid 1 h (docs/06 §2)
# Progressive lockout (EC-ACC-05): lock after N failures, doubling from the base duration.
ACCOUNT_LOCKOUT_THRESHOLD = 10
ACCOUNT_LOCKOUT_BASE_MINUTES = 15
ACCOUNT_LOCKOUT_MAX_MINUTES = 24 * 60

HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/verify-email?key={{key}}",
    "account_reset_password_from_key": f"{FRONTEND_URL}/reset-password?key={{key}}",
    "account_signup": f"{FRONTEND_URL}/register",
    "account_reset_password": f"{FRONTEND_URL}/forgot-password",
}

MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "MUDHOTECH HR RECRUITING SYSTEM"
MFA_RECOVERY_CODE_COUNT = 10
USERSESSIONS_TRACK_ACTIVITY = True
