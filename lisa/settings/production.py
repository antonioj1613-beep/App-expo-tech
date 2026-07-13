"""Production settings."""
import os

from .base import *  # noqa: F403

DEBUG = False

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Security headers (enable when serving over HTTPS).
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "True").lower() in ("true", "1", "yes")  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Vercel terminates TLS at the edge — avoid redirect loops.
# Preview hostnames rotate every deploy, so allow all hosts on Vercel.
if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    SECURE_SSL_REDIRECT = False
    ALLOWED_HOSTS = ["*"]  # noqa: F405
