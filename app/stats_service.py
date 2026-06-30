"""Aggregate and refresh learner stats from sessions and progress rows."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Sum
from django.utils import timezone

from .models import Skill, SpeakingSession, User, UserProfile, UserSkillProgress
from .user_helpers import ensure_profile

# ---------------------------------------------------------------------------
# Speaking XP / accuracy (provisional — no prior logic existed in the app).
# Adjust these constants to match your gamification rules.
# ---------------------------------------------------------------------------
SPEAKING_XP_PER_USER_TURN = 15
SPEAKING_SESSION_COMPLETE_BONUS = 25
SPEAKING_MIN_TURNS_FOR_BONUS = 2


def estimate_turn_accuracy(message: str) -> int:
    """Engagement-based proxy until real pronunciation/grammar scoring exists."""
    words = len(message.split())
    if words < 2:
        return 40
    return min(100, 50 + words * 5)


def compute_speaking_session_stats(transcript: list[dict]) -> dict:
    """Return xp_earned, accuracy_score, user_turn_count from a transcript."""
    user_messages = [
        str(item.get("content", "")).strip()
        for item in transcript
        if isinstance(item, dict) and item.get("role") == "user" and str(item.get("content", "")).strip()
    ]
    turn_count = len(user_messages)
    xp = turn_count * SPEAKING_XP_PER_USER_TURN
    if turn_count >= SPEAKING_MIN_TURNS_FOR_BONUS:
        xp += SPEAKING_SESSION_COMPLETE_BONUS

    accuracy = None
    if user_messages:
        scores = [estimate_turn_accuracy(msg) for msg in user_messages]
        accuracy = round(sum(scores) / len(scores), 2)

    return {
        "xp_earned": xp,
        "accuracy_score": accuracy,
        "user_turn_count": turn_count,
    }


SKILL_SEED_DATA = [
    {"name": "Listening", "slug": "listening", "total_lessons": 60},
    {"name": "Reading", "slug": "reading", "total_lessons": 52},
    {"name": "Writing", "slug": "writing", "total_lessons": 44},
    {"name": "Vocabulary", "slug": "vocabulary", "total_lessons": 280},
    {"name": "Speaking", "slug": "speaking", "total_lessons": 30},
]

SKILL_UI_META = {
    "listening": {"icon": "headphones", "url": "listening"},
    "reading": {"icon": "book-open", "url": "reading"},
    "writing": {"icon": "pen-line", "url": "writing"},
    "vocabulary": {"icon": "graduation-cap", "url": "vocabulary"},
    "speaking": {"icon": "mic", "url": "speaking"},
}


def seed_skills() -> list[Skill]:
    skills = []
    for row in SKILL_SEED_DATA:
        skill, _ = Skill.objects.update_or_create(
            slug=row["slug"],
            defaults={"name": row["name"], "total_lessons": row["total_lessons"]},
        )
        skills.append(skill)
    return skills


def ensure_user_skill_progress(user: User) -> None:
    """Create progress rows for every skill (idempotent)."""
    for skill in Skill.objects.all():
        UserSkillProgress.objects.get_or_create(
            user=user,
            skill=skill,
            defaults={"status": UserSkillProgress.Status.NOT_STARTED},
        )


def refresh_profile_stats(user: User) -> UserProfile:
    """
    Recompute cached profile fields from SpeakingSession aggregates.

    avg_accuracy and study_hours are stored on UserProfile for fast dashboard reads;
    they are refreshed whenever a speaking session is saved. Other skills will hook
    into the same method when lesson completion is implemented.
    """
    profile = ensure_profile(user)
    session_agg = SpeakingSession.objects.filter(user=user).aggregate(
        total_xp=Sum("xp_earned"),
        avg_accuracy=Avg("accuracy_score"),
        total_seconds=Sum("duration_seconds"),
    )

    profile.total_xp = session_agg["total_xp"] or 0
    profile.avg_accuracy = session_agg["avg_accuracy"]
    seconds = session_agg["total_seconds"] or 0
    profile.study_hours = Decimal(seconds) / Decimal(3600)
    profile.study_hours = profile.study_hours.quantize(Decimal("0.01"))

    today = timezone.localdate()
    if SpeakingSession.objects.filter(user=user).exists():
        _update_streak(profile, today)
        profile.last_active_date = today

    profile.save(
        update_fields=[
            "total_xp",
            "avg_accuracy",
            "study_hours",
            "last_active_date",
            "streak_days",
            "updated_at",
        ]
    )
    return profile


def _update_streak(profile: UserProfile, today) -> None:
    last = profile.last_active_date
    if last is None:
        profile.streak_days = max(1, profile.streak_days or 1)
        return
    if last == today:
        return
    if (today - last).days == 1:
        profile.streak_days += 1
    else:
        profile.streak_days = 1


def record_speaking_session(
    user: User,
    *,
    tutor: str,
    transcript: list[dict],
    duration_seconds: int,
) -> SpeakingSession:
    stats = compute_speaking_session_stats(transcript)
    session = SpeakingSession.objects.create(
        user=user,
        tutor=tutor if tutor in ("Miles", "Maya") else "Miles",
        transcript=transcript,
        accuracy_score=stats["accuracy_score"],
        xp_earned=stats["xp_earned"],
        duration_seconds=max(0, duration_seconds),
    )

    speaking_skill = Skill.objects.filter(slug="speaking").first()
    if speaking_skill and stats["user_turn_count"] > 0:
        progress, _ = UserSkillProgress.objects.get_or_create(
            user=user,
            skill=speaking_skill,
            defaults={"status": UserSkillProgress.Status.NOT_STARTED},
        )
        progress.lessons_completed += 1
        progress.sync_status_and_level()
        progress.save(update_fields=["lessons_completed", "status", "level", "last_updated"])

    refresh_profile_stats(user)
    return session


def format_number(value: int) -> str:
    return f"{value:,}"


def format_study_hours(hours: Decimal | float) -> str:
    h = Decimal(str(hours)).quantize(Decimal("0.1"))
    if h < Decimal("1"):
        return "0h"
    if h == h.to_integral():
        return f"{int(h)}h"
    return f"{h}h"


def format_accuracy(accuracy) -> str:
    if accuracy is None:
        return "—"
    return f"{Decimal(str(accuracy)).quantize(Decimal('1'))}%"


def get_skill_progress_row(user: User, slug: str) -> UserSkillProgress | None:
    return (
        UserSkillProgress.objects.select_related("skill")
        .filter(user=user, skill__slug=slug)
        .first()
    )


def build_skill_context(user: User, slug: str) -> dict:
    progress = get_skill_progress_row(user, slug)
    meta = SKILL_UI_META.get(slug, {})
    if not progress:
        seed = next((s for s in SKILL_SEED_DATA if s["slug"] == slug), None)
        total = seed["total_lessons"] if seed else 0
        return {
            "level": 1,
            "status": "Not started",
            "progress_percent": 0,
            "lessons_completed": 0,
            "total_lessons": total,
            "lessons_label": f"0 / {total}",
            "subtitle": f"Level 1 · Not started",
            **meta,
        }

    skill = progress.skill
    status = progress.status_label
    return {
        "level": progress.level,
        "status": status,
        "progress_percent": progress.progress_percent,
        "lessons_completed": progress.lessons_completed,
        "total_lessons": skill.total_lessons,
        "lessons_label": f"{progress.lessons_completed} / {skill.total_lessons}",
        "subtitle": f"Level {progress.level} · {status}",
        **meta,
    }


def build_skills_dashboard_list(user: User) -> list[dict]:
    ensure_user_skill_progress(user)
    rows = []
    for progress in UserSkillProgress.objects.select_related("skill").filter(user=user):
        slug = progress.skill.slug
        meta = SKILL_UI_META.get(slug, {})
        rows.append(
            {
                "name": progress.skill.name,
                "slug": slug,
                "url": meta.get("url", slug),
                "icon": meta.get("icon", "layers"),
                "progress": progress.progress_percent,
                "level": progress.level,
                "status": progress.status_label,
                "lessons_label": f"{progress.lessons_completed} / {progress.skill.total_lessons}",
            }
        )
    order = [s["slug"] for s in SKILL_SEED_DATA]
    rows.sort(key=lambda r: order.index(r["slug"]) if r["slug"] in order else 99)
    return rows


def build_progress_skills_list(user: User) -> list[dict]:
    return [
        {
            "icon": s["icon"],
            "n": s["name"],
            "p": s["progress"],
            "lv": s["level"],
            "lessons": s["lessons_label"],
            "status": s["status"],
        }
        for s in build_skills_dashboard_list(user)
    ]
