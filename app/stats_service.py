"""Aggregate and refresh learner stats — single source of truth for all skills."""

from __future__ import annotations

from calendar import month_abbr
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Sum
from django.utils import timezone

from .gamification import (
    CEFR_ROLLING_WINDOW,
    DAILY_LESSON_GOAL,
    STREAK_FREEZE_EARN_INTERVAL_DAYS,
    STREAK_FREEZE_MAX_STORED,
    VOCABULARY_MASTERY_REPETITIONS,
    compute_speaking_session_xp,
    derive_overall_cefr_level,
    estimate_speaking_turn_accuracy,
    recompute_cefr_level,
)
from .models import (
    PracticeSession,
    Skill,
    SkillLesson,
    SpeakingSession,
    STAFF_SKILL_SLUGS,
    User,
    UserProfile,
    UserSkillProgress,
    UserVocabularyReviewState,
)
from .user_helpers import ensure_profile

SKILL_SEED_DATA = [
    # total_lessons here is only a fallback default used before any
    # SkillLesson exists for a skill (see build_skill_context) — for the
    # four staff-managed skills, sync_skill_lesson_count (signals.py)
    # overwrites this with the real published-lesson count on every
    # SkillLesson save/delete, so keep these roughly in sync with the
    # seed_*.py catalogs to avoid a stale value between seeding and a
    # user's next registration (which re-runs seed_skills()).
    {"name": "Listening", "slug": "listening", "total_lessons": 60},
    {"name": "Reading", "slug": "reading", "total_lessons": 53},
    {"name": "Writing", "slug": "writing", "total_lessons": 34},
    {"name": "Vocabulary", "slug": "vocabulary", "total_lessons": 270},
    {"name": "Speaking", "slug": "speaking", "total_lessons": 30},
]

SKILL_UI_META = {
    "listening": {"icon": "headphones", "url": "listening"},
    "reading": {"icon": "book-open", "url": "reading"},
    "writing": {"icon": "pen-line", "url": "writing"},
    "vocabulary": {"icon": "graduation-cap", "url": "vocabulary"},
    "speaking": {"icon": "mic", "url": "speaking"},
}

PIE_CHART_COLORS = [
    "rgb(182 112 255)",
    "rgb(0 160 255)",
    "rgb(247 112 239)",
    "rgb(0 198 213)",
    "rgb(0 199 105)",
]


def cefr_display(level: str | None) -> str:
    """Human-facing text for a CEFR level that may be unassessed."""
    return level or "Unassessed"


# ---------------------------------------------------------------------------
# Skill seeding & progress rows
# ---------------------------------------------------------------------------


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
    for skill in Skill.objects.all():
        UserSkillProgress.objects.get_or_create(
            user=user,
            skill=skill,
            defaults={"status": UserSkillProgress.Status.NOT_STARTED},
        )


# ---------------------------------------------------------------------------
# Speaking session recording
# ---------------------------------------------------------------------------


def compute_speaking_session_stats(transcript: list[dict]) -> dict:
    user_messages = [
        str(item.get("content", "")).strip()
        for item in transcript
        if isinstance(item, dict) and item.get("role") == "user" and str(item.get("content", "")).strip()
    ]
    turn_count = len(user_messages)
    xp = compute_speaking_session_xp(turn_count)

    accuracy = None
    if user_messages:
        scores = [estimate_speaking_turn_accuracy(msg) for msg in user_messages]
        accuracy = round(sum(scores) / len(scores), 2)

    return {
        "xp_earned": xp,
        "accuracy_score": accuracy,
        "user_turn_count": turn_count,
    }


def _increment_skill_lessons(user: User, skill_slug: str, count: int = 1) -> None:
    skill = Skill.objects.filter(slug=skill_slug).first()
    if not skill or count <= 0:
        return
    progress, _ = UserSkillProgress.objects.get_or_create(
        user=user,
        skill=skill,
        defaults={"status": UserSkillProgress.Status.NOT_STARTED},
    )
    progress.lessons_completed += count
    progress.sync_status()
    progress.save(update_fields=["lessons_completed", "status", "last_updated"])


def recompute_skill_cefr_level(user: User, skill_slug: str) -> str | None:
    """Recompute a skill's CEFR level from its rolling accuracy window.
    Called after every graded interaction — see record_practice_session."""
    skill = Skill.objects.filter(slug=skill_slug).first()
    if not skill:
        return None

    progress, _ = UserSkillProgress.objects.get_or_create(
        user=user,
        skill=skill,
        defaults={"status": UserSkillProgress.Status.NOT_STARTED},
    )
    qs = (
        PracticeSession.objects.filter(user=user, skill=skill, accuracy_score__isnull=False)
        .order_by("-created_at")
        .values_list("accuracy_score", "lesson_level")
    )
    total_count = qs.count()
    rolling_pairs = [(float(accuracy), lesson_level) for accuracy, lesson_level in qs[:CEFR_ROLLING_WINDOW]]

    new_level = recompute_cefr_level(
        rolling_pairs,
        total_interaction_count=total_count,
        current_level=progress.cefr_level,
    )
    if new_level != progress.cefr_level:
        progress.cefr_level = new_level
        progress.save(update_fields=["cefr_level", "last_updated"])
    return new_level


def record_practice_session(
    user: User,
    *,
    skill_slug: str,
    xp_earned: int,
    accuracy_score: Decimal | float | None = None,
    duration_seconds: int = 0,
    lessons_completed: int = 0,
    lesson_level: int | None = None,
) -> PracticeSession:
    skill = Skill.objects.filter(slug=skill_slug).first()
    if not skill:
        raise ValueError(f"Unknown skill slug: {skill_slug}")

    session = PracticeSession.objects.create(
        user=user,
        skill=skill,
        xp_earned=max(0, xp_earned),
        accuracy_score=accuracy_score,
        duration_seconds=max(0, duration_seconds),
        lesson_level=lesson_level,
    )

    if lessons_completed > 0:
        _increment_skill_lessons(user, skill_slug, lessons_completed)

    if accuracy_score is not None:
        recompute_skill_cefr_level(user, skill_slug)

    refresh_profile_stats(user)
    return session


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

    lessons = 1 if stats["user_turn_count"] > 0 else 0
    record_practice_session(
        user,
        skill_slug="speaking",
        xp_earned=stats["xp_earned"],
        accuracy_score=stats["accuracy_score"],
        duration_seconds=duration_seconds,
        lessons_completed=lessons,
    )
    return session


def finalize_speaking_session(
    session: SpeakingSession,
    *,
    duration_seconds: int,
) -> SpeakingSession:
    """Score and persist an in-progress SpeakingSession created at session start."""
    stats = compute_speaking_session_stats(session.transcript)
    session.accuracy_score = stats["accuracy_score"]
    session.xp_earned = stats["xp_earned"]
    session.duration_seconds = max(0, duration_seconds)
    session.save(update_fields=["accuracy_score", "xp_earned", "duration_seconds"])

    lessons = 1 if stats["user_turn_count"] > 0 else 0
    record_practice_session(
        session.user,
        skill_slug="speaking",
        xp_earned=stats["xp_earned"],
        accuracy_score=stats["accuracy_score"],
        duration_seconds=duration_seconds,
        lessons_completed=lessons,
    )
    return session


# ---------------------------------------------------------------------------
# Vocabulary mastery (words_learned) — Phase 2, SM-2 spaced repetition.
# Review scheduling itself lives in vocabulary_service.py; this is just the
# words_learned/profile-stat bookkeeping, same role it always had.
# ---------------------------------------------------------------------------


def sync_words_learned(user: User) -> int:
    """A word counts toward words_learned once it's survived
    VOCABULARY_MASTERY_REPETITIONS successful SM-2 repetitions in a row."""
    count = UserVocabularyReviewState.objects.filter(
        user=user, repetition_count__gte=VOCABULARY_MASTERY_REPETITIONS
    ).count()
    profile = ensure_profile(user)
    if profile.words_learned != count:
        profile.words_learned = count
        profile.save(update_fields=["words_learned", "updated_at"])
    return count


def vocabulary_stats_for_user(user: User) -> dict:
    sync_words_learned(user)
    profile = ensure_profile(user)
    mastered = profile.words_learned
    total_words = SkillLesson.objects.filter(skill__slug="vocabulary", is_published=True).count()
    # Due includes mastered words too — SM-2 keeps scheduling reviews
    # indefinitely (with a growing interval), mastery is a display
    # milestone, not an exit from the review cycle.
    review_due = UserVocabularyReviewState.objects.filter(
        user=user, next_review_date__lte=timezone.localdate()
    ).count()
    return {
        "learned": mastered,
        "mastered": mastered,
        "review_due": review_due,
        "total_words": total_words,
        "profile_words_learned": profile.words_learned,
    }


# ---------------------------------------------------------------------------
# Profile cache refresh
# ---------------------------------------------------------------------------


def refresh_profile_stats(user: User) -> UserProfile:
    profile = ensure_profile(user)
    session_agg = PracticeSession.objects.filter(user=user).aggregate(
        total_xp=Sum("xp_earned"),
        avg_accuracy=Avg("accuracy_score"),
        total_seconds=Sum("duration_seconds"),
    )

    profile.total_xp = session_agg["total_xp"] or 0
    profile.avg_accuracy = session_agg["avg_accuracy"]
    seconds = session_agg["total_seconds"] or 0
    profile.study_hours = (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))

    today = timezone.localdate()
    if PracticeSession.objects.filter(user=user).exists():
        _update_streak(profile, today)
        profile.last_active_date = today

    sync_words_learned(user)
    profile.refresh_from_db(fields=["words_learned"])

    profile.save(
        update_fields=[
            "total_xp",
            "avg_accuracy",
            "study_hours",
            "last_active_date",
            "streak_days",
            "streak_freezes",
            "last_freeze_consumed_at",
            "words_learned",
            "updated_at",
        ]
    )
    return profile


def _update_streak(profile: UserProfile, today) -> None:
    """
    Evaluated lazily, in-request, at the same point streak_days has always
    been updated — this app has no scheduler, so a missed day is only ever
    detected the next time the user is actually active again.

    A freeze only ever covers a gap of exactly one missed day (gap == 2).
    Freezes deliberately do NOT stack for longer gaps: with no way to warn a
    user mid-absence, silently burning the whole freeze bank on one long
    disappearance would spend it with no chance for the user to have made a
    different call. A 2+ day gap always hard-resets, freezes untouched.
    """
    last = profile.last_active_date
    if last is None:
        profile.streak_days = max(1, profile.streak_days or 1)
        return
    if last == today:
        return

    gap = (today - last).days
    if gap == 1:
        profile.streak_days += 1
    elif gap == 2 and profile.streak_freezes > 0:
        profile.streak_freezes -= 1
        profile.streak_days += 1
        profile.last_freeze_consumed_at = timezone.now()
    else:
        profile.streak_days = 1
        return  # a reset never earns a freeze in the same tick

    if profile.streak_days % STREAK_FREEZE_EARN_INTERVAL_DAYS == 0:
        profile.streak_freezes = min(STREAK_FREEZE_MAX_STORED, profile.streak_freezes + 1)


# ---------------------------------------------------------------------------
# Chart & dashboard aggregations
# ---------------------------------------------------------------------------


def weekly_xp_data(user: User) -> list[int]:
    """XP per weekday (Mon–Sun) for the current calendar week."""
    today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    buckets = [0] * 7
    sessions = PracticeSession.objects.filter(
        user=user,
        created_at__date__gte=monday,
        created_at__date__lte=monday + timedelta(days=6),
    )
    for session in sessions:
        day_index = (session.created_at.date() - monday).days
        if 0 <= day_index < 7:
            buckets[day_index] += session.xp_earned
    return buckets


def monthly_xp_data(user: User, months: int = 8) -> tuple[list[str], list[int]]:
    """XP per calendar month for the last `months` months (oldest first)."""
    today = timezone.localdate()
    labels: list[str] = []
    data: list[int] = []

    for offset in range(months - 1, -1, -1):
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        labels.append(month_abbr[month])
        start = timezone.datetime(year, month, 1, tzinfo=timezone.get_current_timezone())
        if month == 12:
            end = timezone.datetime(year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
        else:
            end = timezone.datetime(year, month + 1, 1, tzinfo=timezone.get_current_timezone())
        total = (
            PracticeSession.objects.filter(user=user, created_at__gte=start, created_at__lt=end)
            .aggregate(total=Sum("xp_earned"))
            .get("total")
            or 0
        )
        data.append(total)
    return labels, data


def weekly_accuracy_trend(user: User, weeks: int = 7) -> tuple[list[str], list[float]]:
    """Average session accuracy per week for the last `weeks` weeks."""
    today = timezone.localdate()
    labels: list[str] = []
    data: list[float] = []

    for offset in range(weeks - 1, -1, -1):
        week_end = today - timedelta(days=today.weekday() + 7 * offset)
        week_start = week_end - timedelta(days=6)
        labels.append(f"W{weeks - offset}")
        avg = (
            PracticeSession.objects.filter(
                user=user,
                created_at__date__gte=week_start,
                created_at__date__lte=week_end,
                accuracy_score__isnull=False,
            ).aggregate(avg=Avg("accuracy_score"))["avg"]
        )
        data.append(float(avg) if avg is not None else 0.0)
    return labels, data


def study_seconds_by_skill_this_month(user: User) -> tuple[list[str], list[int]]:
    """Practice seconds grouped by skill for the current calendar month (pie chart)."""
    today = timezone.localdate()
    start = timezone.datetime(today.year, today.month, 1, tzinfo=timezone.get_current_timezone())
    rows = (
        PracticeSession.objects.filter(user=user, created_at__gte=start)
        .values("skill__name", "skill__slug")
        .annotate(total_seconds=Sum("duration_seconds"))
        .order_by("skill__slug")
    )
    labels = [row["skill__name"] for row in rows if row["total_seconds"]]
    data = [row["total_seconds"] for row in rows if row["total_seconds"]]
    if not labels:
        skills = Skill.objects.exclude(slug="speaking").order_by("slug")[:4]
        labels = [s.name for s in skills]
        data = [0] * len(labels)
    return labels, data


def lessons_completed_today(user: User) -> int:
    today = timezone.localdate()
    return PracticeSession.objects.filter(user=user, created_at__date=today).count()


def xp_in_date_range(user: User, start_date, end_date) -> int:
    total = (
        PracticeSession.objects.filter(
            user=user,
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        ).aggregate(total=Sum("xp_earned"))["total"]
        or 0
    )
    return total


def trend_label(current: int, previous: int, *, unit: str = "") -> str:
    if previous <= 0:
        return "No prior data" if current <= 0 else "New activity"
    delta = current - previous
    pct = round(delta * 100 / previous)
    sign = "+" if delta >= 0 else ""
    suffix = f" {unit}".strip()
    return f"{sign}{pct}% vs last month{suffix}"


def build_statistics_cards(user: User, profile: UserProfile) -> list[dict]:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    if month_start.month == 1:
        prev_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_start = month_start.replace(month=month_start.month - 1)
    prev_end = month_start - timedelta(days=1)

    xp_this = xp_in_date_range(user, month_start, today)
    xp_prev = xp_in_date_range(user, prev_start, prev_end)

    return [
        {
            "l": "Total XP",
            "v": format_number(profile.total_xp),
            "d": trend_label(xp_this, xp_prev),
            "trend": "success" if xp_this >= xp_prev else "primary",
        },
        {
            "l": "Avg accuracy",
            "v": format_accuracy(profile.avg_accuracy),
            "d": "From scored sessions",
            "trend": "success",
        },
        {
            "l": "Study hours",
            "v": format_study_hours(profile.study_hours),
            "d": "Time practicing",
            "trend": "success",
        },
        {
            "l": "Words learned",
            "v": format_number(profile.words_learned),
            "d": "Vocabulary mastery",
            "trend": "primary",
        },
    ]


def build_daily_goal_context(user: User) -> dict:
    completed = lessons_completed_today(user)
    goal = DAILY_LESSON_GOAL
    remaining = max(0, goal - completed)
    percent = min(100, round(completed * 100 / goal)) if goal else 0
    if remaining == 0:
        headline = "You hit your daily goal — great work!"
    elif remaining == 1:
        headline = "Just 1 more lesson to hit your goal today."
    else:
        headline = f"Just {remaining} more lessons to hit your goal today."
    return {
        "daily_lessons_completed": completed,
        "daily_lesson_goal": goal,
        "daily_goal_percent": percent,
        "daily_goal_headline": headline,
        "daily_goal_on_track": completed >= goal or completed >= goal - 1,
    }


def build_recent_achievements(user: User, limit: int = 3) -> list[dict]:
    profile = ensure_profile(user)
    achievements: list[dict] = []

    if profile.streak_days >= 7:
        achievements.append(
            {
                "icon": "flame",
                "t": f"{profile.streak_days}-day streak",
                "d": "Keep it going",
                "c": "text-warning bg-warning/15",
            }
        )
    elif profile.streak_days >= 3:
        achievements.append(
            {
                "icon": "flame",
                "t": f"{profile.streak_days}-day streak",
                "d": "Building momentum",
                "c": "text-warning bg-warning/15",
            }
        )

    if profile.last_freeze_consumed_at:
        when = _relative_time(profile.last_freeze_consumed_at)
        # Bounded to the same "still fresh" window the notifications feed
        # already uses for the "new" badge (see is_recent in
        # build_notification_items) — a past event, not an ongoing status
        # like the streak/XP rows above, so it must stop being synthesized
        # once it's no longer recent, not persist forever.
        if when == "Just now" or when.endswith("h ago") or when == "Yesterday":
            achievements.append(
                {
                    "icon": "snowflake",
                    "t": "Streak freeze used — your streak was saved",
                    "d": when,
                    "c": "text-accent bg-accent/15",
                }
            )

    if profile.total_xp >= 1000:
        achievements.append(
            {
                "icon": "star",
                "t": "First 1,000 XP",
                "d": "Milestone unlocked",
                "c": "text-primary bg-primary/15",
            }
        )

    recent = PracticeSession.objects.select_related("skill").filter(user=user).order_by("-created_at")[:5]
    for session in recent:
        when = _relative_time(session.created_at)
        achievements.append(
            {
                "icon": "mic" if session.skill.slug == "speaking" else "trophy",
                "t": f"{session.skill.name} practice (+{session.xp_earned} XP)",
                "d": when,
                "c": "text-success bg-success/15",
            }
        )

    return achievements[:limit]


def _relative_time(dt) -> str:
    now = timezone.now()
    delta = now - dt
    if delta.days == 0:
        hours = delta.seconds // 3600
        if hours == 0:
            return "Just now"
        return f"{hours}h ago"
    if delta.days == 1:
        return "Yesterday"
    if delta.days < 7:
        return f"{delta.days}d ago"
    return dt.strftime("%b %d")


# ---------------------------------------------------------------------------
# Display helpers & skill context
# ---------------------------------------------------------------------------


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


def profile_stats_cards(profile: UserProfile) -> list[dict]:
    return [
        {"label": "Total XP", "value": format_number(profile.total_xp), "suffix": "", "icon": "zap", "color": "text-primary"},
        {
            "label": "Avg accuracy",
            "value": format_accuracy(profile.avg_accuracy).replace("%", ""),
            "suffix": "%" if profile.avg_accuracy is not None else "",
            "icon": "target",
            "color": "text-success",
        },
        {"label": "Study hours", "value": format_study_hours(profile.study_hours), "suffix": "", "icon": "clock", "color": "text-accent"},
        {"label": "Words learned", "value": format_number(profile.words_learned), "suffix": "", "icon": "book-open", "color": "text-warning"},
    ]


def leaderboard_rows(user: User, limit: int = 50) -> dict:
    """
    Global ranking by UserProfile.total_xp -- the only XP figure the app
    has (there is no derived "level" number anywhere; CEFR level is
    per-skill, not a points ranking, see gamification.py). Deliberately a
    read-only aggregate over existing data, no new field/model needed.
    """
    profiles = list(
        UserProfile.objects.select_related("user")
        .order_by("-total_xp", "user__created_at")
        .values("user_id", "user__username", "total_xp", "streak_days")
    )

    rows = [
        {
            "rank": i + 1,
            "user_id": p["user_id"],
            "username": p["user__username"],
            "total_xp": p["total_xp"],
            "streak_days": p["streak_days"],
            "is_you": p["user_id"] == user.id,
        }
        for i, p in enumerate(profiles[:limit])
    ]

    your_row = next((r for r in rows if r["is_you"]), None)
    if your_row is None:
        for i, p in enumerate(profiles):
            if p["user_id"] == user.id:
                your_row = {
                    "rank": i + 1,
                    "user_id": p["user_id"],
                    "username": p["user__username"],
                    "total_xp": p["total_xp"],
                    "streak_days": p["streak_days"],
                    "is_you": True,
                }
                break

    return {"rows": rows, "your_row": your_row, "total_ranked": len(profiles)}


def build_app_user_stats(user: User) -> dict:
    """Sidebar / header learner widget — single source for the derived
    overall CEFR level and XP. Level is now the median of assessed per-skill
    CEFR levels (see gamification.derive_overall_cefr_level), display-only —
    it does not drive anything (Speaking's tutor difficulty reads its own
    skill-level CEFR directly, not this derived value). XP/streak are their
    own independent stats and no longer imply a level."""
    from .user_helpers import is_new_user, user_initials

    profile = ensure_profile(user)
    new_user = is_new_user(user)
    total_xp = profile.total_xp
    skill_levels = list(UserSkillProgress.objects.filter(user=user).values_list("cefr_level", flat=True))
    overall_level = None if new_user else derive_overall_cefr_level(skill_levels)

    return {
        "username": user.username,
        "display_name": user.username.replace("_", " ").title(),
        "initials": user_initials(user.username),
        "is_new": new_user,
        "streak_days": profile.streak_days,
        "streak_freezes": profile.streak_freezes,
        "total_xp": total_xp,
        "total_xp_display": format_number(total_xp),
        "level": overall_level,
        "level_label": "New learner" if new_user else cefr_display(overall_level),
    }


DASHBOARD_STARTER_LESSONS = [
    {
        "tag": "Speaking",
        "tag_tone": "success",
        "title": "Greetings & introductions",
        "duration": "5 min",
        "url": "speaking",
    },
    {
        "tag": "Vocabulary",
        "tag_tone": "primary",
        "title": "Everyday vocabulary",
        "duration": "6 min",
        "url": "vocabulary",
    },
    {
        "tag": "Listening",
        "tag_tone": "accent",
        "title": "Your first guided dialogue",
        "duration": "7 min",
        "url": "listening",
    },
]


def build_dashboard_new_user_context(user: User, *, first_name: str, page_title: str) -> dict:
    profile = ensure_profile(user)
    tasks = profile_setup_tasks()
    return {
        "active": "dashboard",
        "is_new_user": True,
        "page_title": page_title,
        "page_subtitle": "Let's take your first steps to personalize your English.",
        "stats": profile_stats_cards(profile),
        "setup_tasks": tasks,
        "setup_done": 0,
        "setup_total": len(tasks),
        "starter_lessons": DASHBOARD_STARTER_LESSONS,
    }


def build_dashboard_returning_context(user: User, *, first_name: str) -> dict:
    ensure_user_skill_progress(user)
    profile = ensure_profile(user)
    week_data = weekly_xp_data(user)
    daily_goal = build_daily_goal_context(user)

    skills = build_skills_dashboard_list(user)
    for s in skills:
        s["level"] = cefr_display(s["level"])

    return {
        "active": "dashboard",
        "is_new_user": False,
        "page_title": "Dashboard",
        "page_subtitle": f"Welcome back, {first_name} — let's keep the streak alive 🔥",
        "stats": profile_stats_cards(profile),
        "skills": skills,
        "week_xp_total": sum(week_data),
        "week_data": week_data,
        "week_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "streak_days": profile.streak_days,
        "achievements": build_recent_achievements(user),
        **daily_goal,
    }


def build_post_practice_payload(
    user: User,
    *,
    skill_slug: str,
    xp_earned: int,
    accuracy_score: float | None = None,
    session_id: int | None = None,
) -> dict:
    """JSON payload for client UI after any skill practice is saved."""
    profile = ensure_profile(user)
    profile.refresh_from_db()
    skill_ctx = build_skill_context(user, skill_slug)
    app_user = build_app_user_stats(user)
    session_count = PracticeSession.objects.filter(user=user).count()

    return {
        "ok": True,
        "ui_mode": "reload" if session_count == 1 else "partial",
        "session": {
            "id": session_id,
            "xp_earned": xp_earned,
            "accuracy_score": accuracy_score,
        },
        "profile": {
            "total_xp": profile.total_xp,
            "avg_accuracy": float(profile.avg_accuracy) if profile.avg_accuracy is not None else None,
            "study_hours": float(profile.study_hours),
            "streak_days": profile.streak_days,
            "words_learned": profile.words_learned,
        },
        "app_user": app_user,
        "skill_progress": {
            "slug": skill_slug,
            "level": skill_ctx["level"],
            "progress_percent": skill_ctx["progress_percent"],
            "lessons_label": skill_ctx["lessons_label"],
            "subtitle": skill_ctx["subtitle"],
            "status": skill_ctx["status"],
        },
        # Backward compatibility for Speaking page
        "speaking_skill": skill_ctx if skill_slug == "speaking" else None,
    }


def build_post_session_payload(user: User, session: SpeakingSession) -> dict:
    """JSON payload for client UI after a speaking session is saved."""
    accuracy = float(session.accuracy_score) if session.accuracy_score is not None else None
    payload = build_post_practice_payload(
        user,
        skill_slug="speaking",
        xp_earned=session.xp_earned,
        accuracy_score=accuracy,
        session_id=session.id,
    )
    payload["speaking_skill"] = payload["skill_progress"]
    return payload


def get_skill_progress_row(user: User, slug: str) -> UserSkillProgress | None:
    return (
        UserSkillProgress.objects.select_related("skill")
        .filter(user=user, skill__slug=slug)
        .first()
    )


def build_skill_context(user: User, slug: str) -> dict:
    ensure_user_skill_progress(user)
    progress = get_skill_progress_row(user, slug)
    meta = SKILL_UI_META.get(slug, {})

    if slug in STAFF_SKILL_SLUGS:
        from .lesson_service import get_skill_page_state

        page_state = get_skill_page_state(user, slug)
        total = page_state["total_lessons"]
        completed = progress.lessons_completed if progress else 0
        progress_percent = min(100, round(completed * 100 / total)) if total else 0

        if not page_state["has_lessons"] or page_state["catalog_complete"]:
            subtitle = page_state["coming_soon_message"]
        elif page_state["next_lesson"]:
            subtitle = f"Level {page_state['next_lesson'].level} · In progress"
        elif progress:
            subtitle = f"{cefr_display(progress.cefr_level)} · {progress.status_label}"
        else:
            subtitle = "Not started"

        return {
            "level": progress.cefr_level if progress else None,
            "status": progress.status_label if progress else "Not started",
            "progress_percent": progress_percent,
            "lessons_completed": completed,
            "total_lessons": total,
            "lessons_label": f"{completed} / {total}" if total else "0 / 0",
            "subtitle": subtitle,
            "has_lessons": page_state["has_lessons"],
            "catalog_complete": page_state["catalog_complete"],
            "coming_soon": page_state["coming_soon"],
            "coming_soon_message": page_state["coming_soon_message"],
            "current_level": page_state["next_lesson"].level if page_state["next_lesson"] else None,
            **meta,
        }

    if not progress:
        seed = next((s for s in SKILL_SEED_DATA if s["slug"] == slug), None)
        total = seed["total_lessons"] if seed else 0
        return {
            "level": None,
            "status": "Not started",
            "progress_percent": 0,
            "lessons_completed": 0,
            "total_lessons": total,
            "lessons_label": f"0 / {total}",
            "subtitle": "Unassessed · Not started",
            **meta,
        }

    skill = progress.skill
    status = progress.status_label
    return {
        "level": progress.cefr_level,
        "status": status,
        "progress_percent": progress.progress_percent,
        "lessons_completed": progress.lessons_completed,
        "total_lessons": skill.total_lessons,
        "lessons_label": f"{progress.lessons_completed} / {skill.total_lessons}",
        "subtitle": f"{cefr_display(progress.cefr_level)} · {status}",
        **meta,
    }


def build_skills_dashboard_list(user: User) -> list[dict]:
    ensure_user_skill_progress(user)
    rows = []
    for progress in UserSkillProgress.objects.select_related("skill").filter(user=user):
        slug = progress.skill.slug
        meta = SKILL_UI_META.get(slug, {})
        if slug in STAFF_SKILL_SLUGS:
            from .lesson_service import has_published_lessons, published_lesson_count

            total = published_lesson_count(slug)
            completed = progress.lessons_completed
            progress_pct = min(100, round(completed * 100 / total)) if total else 0
            lessons_label = f"{completed} / {total}" if total else "0 / 0"
        else:
            progress_pct = progress.progress_percent
            lessons_label = f"{progress.lessons_completed} / {progress.skill.total_lessons}"
        rows.append(
            {
                "name": progress.skill.name,
                "slug": slug,
                "url": meta.get("url", slug),
                "icon": meta.get("icon", "layers"),
                "progress": progress_pct,
                "level": progress.cefr_level,
                "status": progress.status_label,
                "lessons_label": lessons_label,
                "has_lessons": has_published_lessons(slug) if slug in STAFF_SKILL_SLUGS else True,
            }
        )
    order = [s["slug"] for s in SKILL_SEED_DATA]
    rows.sort(key=lambda r: order.index(r["slug"]) if r["slug"] in order else 99)
    return rows


def build_progress_skills_list(user: User) -> list[dict]:
    """`lv` is the raw CEFR level (or None) — callers needing display text
    should use stats_service.cefr_display(), e.g. for the overall-level
    median calc in views.progress() vs. per-skill row rendering."""
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


def build_notification_items(user: User, limit: int = 10) -> list[dict]:
    """Map recent achievements / practice into notification rows."""
    items = []
    for row in build_recent_achievements(user, limit=limit):
        is_recent = row["d"] in ("Just now",) or row["d"].endswith("h ago") or row["d"] == "Yesterday"
        items.append(
            {
                "icon": row["icon"],
                "t": row["t"],
                "d": row["d"],
                "new": is_recent,
                "c": row["c"],
            }
        )
    return items


def profile_setup_tasks() -> list[dict]:
    return [
        {
            "title": "Take the level test",
            "description": "Find your starting point so lessons match your level.",
            "url": "levels",
            "button": "Start",
        },
        {
            "title": "Choose your goal",
            "description": "Tell us why you're learning — work, travel, exams, or fun.",
            "url": "settings",
            "button": "Choose",
        },
        {
            "title": "Complete your first lesson",
            "description": "Try Speaking or Listening to unlock progress tracking.",
            "url": "speaking",
            "button": "Go",
        },
    ]


def notification_preview_hints() -> list[dict]:
    return [
        {
            "icon": "flame",
            "t": "Streak reminders",
            "d": "We'll nudge you when you're close to losing your streak.",
            "c": "text-warning",
        },
        {
            "icon": "trophy",
            "t": "Achievements & XP",
            "d": "Badges and milestones appear after lessons and practice sessions.",
            "c": "text-primary",
        },
        {
            "icon": "sparkles",
            "t": "New content",
            "d": "Get notified when new lessons unlock in your skill paths.",
            "c": "text-accent",
        },
    ]


def backfill_practice_sessions_from_speaking() -> int:
    """One-off: create PracticeSession rows from legacy SpeakingSession data."""
    created = 0
    speaking_skill = Skill.objects.filter(slug="speaking").first()
    if not speaking_skill:
        return 0

    for session in SpeakingSession.objects.select_related("user").iterator():
        exists = PracticeSession.objects.filter(
            user=session.user,
            skill=speaking_skill,
            xp_earned=session.xp_earned,
            created_at=session.created_at,
        ).exists()
        if exists:
            continue
        PracticeSession.objects.create(
            user=session.user,
            skill=speaking_skill,
            xp_earned=session.xp_earned,
            accuracy_score=session.accuracy_score,
            duration_seconds=session.duration_seconds,
            created_at=session.created_at,
        )
        created += 1
    return created
