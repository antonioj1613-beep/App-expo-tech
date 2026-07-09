"""Pick Django settings module for local vs Vercel/serverless runtimes."""

from __future__ import annotations

import os

_SERVERLESS_KEYS = (
    "VERCEL",
    "VERCEL_ENV",
    "AWS_LAMBDA_FUNCTION_NAME",
    "LAMBDA_TASK_ROOT",
    "AWS_EXECUTION_ENV",
)


def is_serverless_runtime() -> bool:
    return any(os.environ.get(key) for key in _SERVERLESS_KEYS)


def configure_settings_module() -> None:
    """
    Vercel may set DJANGO_SETTINGS_MODULE=development in the dashboard.
    setdefault() cannot override that — force production on serverless instead.
    """
    if is_serverless_runtime():
        os.environ["DJANGO_SETTINGS_MODULE"] = "lisa.settings.production"
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lisa.settings.production")
