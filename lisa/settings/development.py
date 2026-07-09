"""Development settings."""
import os

from .base import *  # noqa: F403

DEBUG = True
# Keep localhost-only hosts for local dev; on Vercel, base.py adds *.vercel.app hosts.
if not os.environ.get("VERCEL"):
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relaxed static storage for dev (no manifest required before collectstatic).
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedStaticFilesStorage"  # noqa: F405
