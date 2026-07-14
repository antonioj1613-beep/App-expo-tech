"""Shared Django settings for Learning Skills."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-me-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

# Always allow any host. Vercel preview URLs change every deploy
# (app-expo-tech-<hash>-learning-skills.vercel.app), so a fixed allowlist breaks.
# Local development is unaffected.
ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
for _key in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_BRANCH_URL"):
    _host = os.environ.get(_key, "").strip().removeprefix("https://").removeprefix("http://")
    if not _host:
        continue
    _origin = f"https://{_host}"
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lisa.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "app" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "app.context_processors.navigation",
                "app.context_processors.app_user",
                "app.context_processors.deployment_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "lisa.wsgi.application"
ASGI_APPLICATION = "lisa.asgi.application"

from lisa.settings._bootstrap import is_serverless_runtime  # noqa: E402
import logging  # noqa: E402
from urllib.parse import parse_qs, unquote, urlparse  # noqa: E402

_settings_log = logging.getLogger(__name__)


def _sqlite_default():
    if is_serverless_runtime():
        return Path(os.environ.get("TMPDIR") or "/tmp") / "learning_skills.sqlite3"
    return BASE_DIR / "db.sqlite3"


def _database_from_url(database_url: str):
    """
    Parse DATABASE_URL for Postgres (Neon/Vercel/Supabase) or SQLite.

    Supports query params such as ?sslmode=require — the old regex treated those
    as part of the DB name and silently fell back to ephemeral SQLite.
    """
    parsed = urlparse(database_url)
    scheme = (parsed.scheme or "").lower()

    if scheme in ("postgres", "postgresql"):
        name = unquote(parsed.path.lstrip("/"))
        # Drop query fragment mistakenly left in path; query is parsed separately.
        if "?" in name:
            name = name.split("?", 1)[0]
        query = parse_qs(parsed.query)
        options = {}
        if "sslmode" in query:
            options["sslmode"] = query["sslmode"][0]
        elif is_serverless_runtime():
            # Managed Postgres (Neon, etc.) requires TLS from serverless hosts.
            options["sslmode"] = "require"

        return {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": name or "postgres",
                "USER": unquote(parsed.username or ""),
                "PASSWORD": unquote(parsed.password or ""),
                "HOST": parsed.hostname or "",
                "PORT": str(parsed.port or 5432),
                "CONN_MAX_AGE": 60 if is_serverless_runtime() else 600,
                "CONN_HEALTH_CHECKS": True,
                "OPTIONS": options,
            }
        }

    if scheme in ("sqlite", "sqlite3"):
        path = unquote(parsed.path)
        # sqlite:////absolute/path or sqlite:///relative.db
        if path.startswith("//"):
            path = path[1:]
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": Path(path) if path else _sqlite_default(),
            }
        }

    return None


# Database — local SQLite by default; set DATABASE_URL for persistent Postgres.
# On Vercel without Postgres, SQLite under /tmp is ephemeral (accounts vanish).
_database_url = os.environ.get("DATABASE_URL", "").strip()
_configured = _database_from_url(_database_url) if _database_url else None
if _configured:
    DATABASES = _configured
else:
    if _database_url:
        _settings_log.error(
            "DATABASE_URL could not be parsed (%s…). Falling back to SQLite.",
            _database_url[:32],
        )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": _sqlite_default(),
        }
    }

USING_POSTGRES = DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"
USING_EPHEMERAL_DATABASE = is_serverless_runtime() and not USING_POSTGRES

if USING_EPHEMERAL_DATABASE:
    _settings_log.critical(
        "Serverless deploy is using ephemeral /tmp SQLite. Accounts and progress "
        "will disappear between cold starts. Set DATABASE_URL to a Postgres URL "
        "(e.g. Neon) in Vercel Environment Variables."
    )

# Cookie sessions avoid read-only SQLite write failures on cold serverless starts.
# With Postgres, use the default DB session backend so sessions stay consistent.
if is_serverless_runtime() and not USING_POSTGRES:
    SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "app" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Use CompressedStaticFilesStorage (not Manifest) — Manifest's staticfiles.json
# breaks Vercel's collectstatic copy step (ENOENT under static/static/).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "landing"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
