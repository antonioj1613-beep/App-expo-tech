"""Pick Django settings module for local vs Vercel/serverless runtimes."""

from __future__ import annotations

import os

_SERVERLESS_KEYS = (
    "VERCEL",
    "VERCEL_ENV",
    "VERCEL_URL",
    "AWS_LAMBDA_FUNCTION_NAME",
    "LAMBDA_TASK_ROOT",
    "AWS_EXECUTION_ENV",
)


def is_serverless_runtime() -> bool:
    return any(os.environ.get(key) for key in _SERVERLESS_KEYS)


def configure_settings_module() -> None:
    """
    Vercel discovers Django via manage.py and may force development settings.
    On serverless, always force production. Locally, prefer development.
    """
    if is_serverless_runtime():
        os.environ["DJANGO_SETTINGS_MODULE"] = "lisa.settings.production"
        return
    # Local: only set a default if nothing is already configured.
    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        os.environ["DJANGO_SETTINGS_MODULE"] = "lisa.settings.development"
