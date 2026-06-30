from datetime import datetime

from .models import PracticeSession, SpeakingSession, User, UserProfile


def get_logged_in_user(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    try:
        return User.objects.select_related("profile").get(pk=user_id)
    except User.DoesNotExist:
        return None


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def is_new_user(user):
    """True when the learner has no activity recorded yet."""
    profile = ensure_profile(user)
    if profile.total_xp > 0 or profile.streak_days > 0:
        return False
    return (
        not user.skill_progress.filter(lessons_completed__gt=0).exists()
        and not SpeakingSession.objects.filter(user=user).exists()
        and not PracticeSession.objects.filter(user=user).exists()
    )


def user_initials(username):
    parts = username.replace("_", " ").replace(".", " ").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return username[:2].upper() if username else "?"


def time_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def build_app_user_context(user):
    from .stats_service import build_app_user_stats

    return build_app_user_stats(user)
