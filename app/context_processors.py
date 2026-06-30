from .levels_service import build_nav_skill_states
from .user_helpers import build_app_user_context, get_logged_in_user


def navigation(request):
    user = get_logged_in_user(request)
    skill_states = build_nav_skill_states(user)
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
    user = get_logged_in_user(request)
    if not user:
        return {"app_user": None}
    return {"app_user": build_app_user_context(user)}
