"""Development settings."""
import os

from .base import *  # noqa: F403

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relaxed static storage for dev (no manifest required before collectstatic).
STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedStaticFilesStorage"  # noqa: F405

# If this module somehow loads on Vercel, never restrict hosts to localhost.
if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    ALLOWED_HOSTS = ["*"]
