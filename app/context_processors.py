import logging

from django.conf import settings
from django.db import DatabaseError, OperationalError

from .levels_service import build_nav_skill_states
from .user_helpers import build_app_user_context, get_logged_in_user

logger = logging.getLogger(__name__)


def deployment_flags(request):
    """Expose hosting/database health flags to every template."""
    return {
        "using_ephemeral_database": bool(getattr(settings, "USING_EPHEMERAL_DATABASE", False)),
        "using_postgres": bool(getattr(settings, "USING_POSTGRES", False)),
    }


def navigation(request):
    try:
        user = get_logged_in_user(request)
        skill_states = build_nav_skill_states(user)
    except (OperationalError, DatabaseError) as exc:
        logger.warning("navigation context skipped (db unavailable): %s", exc)
        user = None
        skill_states = {}

    learn_items = [
        {"name": "dashboard", "title": "Dashboard", "icon": "layout-dashboard"},
        {"name": "levels", "title": "Levels", "icon": "layers"},
        {"name": "listening", "title": "Listening", "icon": "headphones"},
        {"name": "reading", "title": "Reading", "icon": "book-open"},
        {"name": "writing", "title": "Writing", "icon": "pen-line"},
        {"name": "vocabulary", "title": "Vocabulary", "icon": "graduation-cap"},
        {"name": "speaking", "title": "Speaking", "icon": "mic"},
    ]
    for item in learn_items:
        state = skill_states.get(item["name"])
        if state:
            item.update(state)

    return {
        "nav_groups": [
            {
                "label": "Learn",
                "items": learn_items,
            },
            {
                "label": "Insights",
                "items": [
                    {"name": "progress", "title": "Progress", "icon": "trending-up"},
                    {"name": "statistics", "title": "Statistics", "icon": "bar-chart-3"},
                ],
            },
            {
                "label": "Account",
                "items": [
                    {"name": "profile", "title": "Profile", "icon": "user"},
                    {"name": "notifications", "title": "Notifications", "icon": "bell"},
                    {"name": "settings", "title": "Settings", "icon": "settings"},
                    {"name": "premium", "title": "Premium", "icon": "crown"},
                ],
            },
        ]
    }


def app_user(request):
    try:
        user = get_logged_in_user(request)
        if not user:
            return {"app_user": None}
        return {"app_user": build_app_user_context(user)}
    except (OperationalError, DatabaseError) as exc:
        logger.warning("app_user context skipped (db unavailable): %s", exc)
        return {"app_user": None}
