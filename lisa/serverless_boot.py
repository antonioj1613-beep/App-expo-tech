"""Cold-start bootstrap for Vercel / serverless runtimes."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from lisa.settings._bootstrap import is_serverless_runtime

logger = logging.getLogger(__name__)

_BOOTED = False


def ensure_serverless_database() -> None:
    """
    Run migrations and seed catalog data once per warm instance.

    Vercel's /var/task filesystem is read-only, so SQLite lives under /tmp.
    Data is ephemeral per instance — fine for demos; use Postgres for real hosting.
    """
    global _BOOTED
    if _BOOTED or not is_serverless_runtime():
        return
    _BOOTED = True

    # Import Django only after settings have been configured by wsgi/asgi.
    from django.core.management import call_command
    from django.db import connection

    try:
        connection.ensure_connection()
        call_command("migrate", interactive=False, run_syncdb=True, verbosity=0)
        call_command("seed_skills", verbosity=0)
        for cmd in ("seed_reading", "seed_listening", "seed_writing", "seed_vocabulary_lessons"):
            try:
                call_command(cmd, verbosity=0)
            except Exception as exc:  # noqa: BLE001 — seeds are optional per command presence
                logger.warning("Optional seed %s skipped: %s", cmd, exc)
        logger.info("Serverless database ready at %s", connection.settings_dict.get("NAME"))
    except Exception:
        logger.exception("Serverless database bootstrap failed")
        # Allow subsequent requests to retry if the first attempt failed.
        _BOOTED = False
        raise


def serverless_sqlite_path() -> Path:
    tmp = Path(os.environ.get("TMPDIR") or os.environ.get("TMP") or "/tmp")
    return tmp / "learning_skills.sqlite3"
