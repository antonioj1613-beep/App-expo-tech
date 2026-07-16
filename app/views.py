from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
import sqlite3
from pathlib import Path

from .auth_utils import check_password, hash_password
from .decorators import login_required
from .levels_service import build_levels_page_skills
from .speaking_views import speaking_page_context
from .models import Skill, User
from .stats_service import (
    build_dashboard_new_user_context,
    build_dashboard_returning_context,
    build_notification_items,
    build_progress_skills_list,
    build_skill_context,
    build_skills_dashboard_list,
    build_statistics_cards,
    ensure_user_skill_progress,
    format_accuracy,
    format_number,
    format_study_hours,
    monthly_xp_data,
    notification_preview_hints,
    profile_setup_tasks,
    profile_stats_cards,
    study_seconds_by_skill_this_month,
    vocabulary_stats_for_user,
    weekly_accuracy_trend,
    weekly_xp_data,
)
from .user_helpers import (
    build_app_user_context,
    ensure_profile,
    get_logged_in_user,
    invalidate_stale_session,
    is_new_user,
    time_greeting,
    user_initials,
)


def _auth_context(mode, **extra):
    return {"mode": mode, **extra}


def _login_session(request, user):
    request.session["user_id"] = user.id
    request.session["username"] = user.username


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
def landing(request):
    about = [
        {"icon": "target", "t": "Skill-first learning", "d": "Build real English ability across listening, reading, writing, and vocabulary — not just drills."},
        {"icon": "layers", "t": "15-level progression", "d": "A clear path from beginner to fluent, with lessons that unlock as you grow."},
        {"icon": "trending-up", "t": "Track every win", "d": "Dashboard, progress charts, and statistics keep you accountable and motivated."},
    ]
    tools = [
        {"icon": "headphones", "t": "Listening", "d": "Real-world audio with smart subtitles.", "url": "listening"},
        {"icon": "book-open", "t": "Reading", "d": "Adaptive comprehension at every level.", "url": "reading"},
        {"icon": "pen-line", "t": "Writing", "d": "AI feedback on every sentence.", "url": "writing"},
        {"icon": "graduation-cap", "t": "Vocabulary", "d": "Spaced repetition tuned by neural ranking.", "url": "vocabulary"},
        {"icon": "layers", "t": "Levels", "d": "Structured progression from beginner to fluent.", "url": "levels"},
        {"icon": "bar-chart-3", "t": "Statistics", "d": "Deep insights into your study habits and accuracy.", "url": "statistics"},
    ]
    features = [
        {"icon": "graduation-cap", "t": "15-level path", "d": "Structured progression from beginner to fluent."},
        {"icon": "zap", "t": "Real-time AI feedback", "d": "Pronunciation, grammar, and tone analyzed instantly."},
        {"icon": "trophy", "t": "Streaks & XP", "d": "Stay motivated with gamified daily goals."},
        {"icon": "star", "t": "Personalized lessons", "d": "Adapts to your weaknesses every day."},
        {"icon": "headphones", "t": "Native audio library", "d": "Thousands of clips from podcasts, films, news."},
        {"icon": "book-open", "t": "Smart vocabulary", "d": "Spaced repetition tuned by neural ranking."},
    ]
    return render(request, "landing.html", {"about": about, "tools": tools, "features": features})


def _ephemeral_db_warning():
    if getattr(settings, "USING_EPHEMERAL_DATABASE", False):
        return (
            "This hosted demo uses a temporary database. Accounts can disappear "
            "after the server restarts. Set DATABASE_URL (Postgres) in Vercel to keep data."
        )
    return None


def login_view(request):
    if request.session.get("user_id"):
        # Stale cookie from an ephemeral DB wipe — clear it instead of bouncing forever.
        if not get_logged_in_user(request):
            invalidate_stale_session(request)
        else:
            return redirect("dashboard")

    ctx = _auth_context("login")
    ephemeral = _ephemeral_db_warning()
    if ephemeral:
        ctx["form_warning"] = ephemeral

    if request.method == "POST":
        login = request.POST.get("login", "").strip()
        password = request.POST.get("password", "")

        if not login or not password:
            ctx["form_warning"] = "Please enter your login information before continuing."
            return render(request, "auth.html", ctx)

        user = User.objects.filter(Q(username__iexact=login) | Q(email__iexact=login)).first()
        if not user or not check_password(password, user.password):
            ctx["form_error"] = "Incorrect username/email or password."
            ctx["login_value"] = login
            return render(request, "auth.html", ctx)

        _login_session(request, user)
        return redirect("dashboard")

    return render(request, "auth.html", ctx)


def register_view(request):
    if request.session.get("user_id"):
        if not get_logged_in_user(request):
            invalidate_stale_session(request)
        else:
            return redirect("dashboard")

    ctx = _auth_context("register")
    ephemeral = _ephemeral_db_warning()
    if ephemeral:
        ctx["form_warning"] = ephemeral

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not username or not email or not password:
            ctx["form_warning"] = "Please fill in all fields before creating an account."
            ctx["username_value"] = username
            ctx["email_value"] = email
            return render(request, "auth.html", ctx)

        if User.objects.filter(username__iexact=username).exists() or User.objects.filter(email__iexact=email).exists():
            ctx["form_error"] = "An account with this username/email already exists."
            ctx["username_value"] = username
            ctx["email_value"] = email
            return render(request, "auth.html", ctx)

        user = User.objects.create(
            username=username,
            email=email,
            password=hash_password(password),
        )
        messages.success(request, "Account created successfully. Please sign in.")
        return redirect("login")

    return render(request, "auth.html", ctx)


def logout_view(request):
    request.session.flush()
    return redirect("login")


def database_browser(request):
    """DEV ONLY — readable database viewer in the browser."""
    if not settings.DEBUG:
        raise Http404

    db_path = Path(settings.DATABASES["default"]["NAME"])
    tables = []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )

    for (name,) in cur.fetchall():
        cur.execute(f"SELECT COUNT(*) FROM [{name}]")
        count = cur.fetchone()[0]
        columns, rows = [], []
        if count:
            cur.execute(f"SELECT * FROM [{name}] LIMIT 100")
            fetched = cur.fetchall()
            columns = fetched[0].keys()
            for row in fetched:
                row_data = []
                for col in columns:
                    val = row[col]
                    if name == "users" and col == "password":
                        val = "[bcrypt hash hidden]"
                    row_data.append(val)
                rows.append(row_data)
        tables.append({"name": name, "count": count, "columns": columns, "rows": rows})

    conn.close()
    return render(request, "database_browser.html", {"tables": tables, "db_path": str(db_path.resolve())})


# ---------------------------------------------------------------------------
# App pages (login required)
# ---------------------------------------------------------------------------
@login_required
def dashboard(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    ensure_user_skill_progress(user)
    new_user = is_new_user(user)
    name = user.username.replace("_", " ").title()
    first_name = name.split()[0]

    if new_user:
        ctx = build_dashboard_new_user_context(
            user,
            first_name=first_name,
            page_title=f"{time_greeting()}, {first_name}",
        )
        return render(request, "dashboard.html", ctx)

    ctx = build_dashboard_returning_context(user, first_name=first_name)
    return render(request, "dashboard.html", ctx)


@login_required
def levels(request):
    user = get_logged_in_user(request)
    skills = build_levels_page_skills(user)

    return render(
        request,
        "levels.html",
        {
            "active": "levels",
            "skills": skills,
            **speaking_page_context(request),
        },
    )


@login_required
def writing(request):
    user = get_logged_in_user(request)
    skill = build_skill_context(user, "writing")
    from .lesson_service import build_lesson_context, get_skill_page_state

    page_state = get_skill_page_state(user, "writing")
    lesson = page_state["next_lesson"]
    ctx = {
        "active": "writing",
        "skill": skill,
        "page_state": page_state,
    }
    if lesson:
        ctx.update(build_lesson_context(lesson, user, "writing"))
    return render(request, "writing.html", ctx)


@login_required
def vocabulary(request):
    user = get_logged_in_user(request)
    skill = build_skill_context(user, "vocabulary")
    from .lesson_service import build_lesson_context, get_skill_page_state

    page_state = get_skill_page_state(user, "vocabulary")
    lesson = page_state["next_lesson"]
    ctx = {
        "active": "vocabulary",
        "skill": skill,
        "page_state": page_state,
        "vocab_stats": vocabulary_stats_for_user(user),
    }
    if lesson:
        ctx.update(build_lesson_context(lesson, user, "vocabulary"))
    stats = [
        {"l": "Learned", "v": str(ctx["vocab_stats"]["learned"])},
        {"l": "Mastered", "v": str(ctx["vocab_stats"]["mastered"])},
        {"l": "Review due", "v": str(ctx["vocab_stats"]["review_due"])},
    ]
    ctx["stats"] = stats
    return render(request, "vocabulary.html", ctx)


@login_required
def progress(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")
    ensure_user_skill_progress(user)
    profile = ensure_profile(user)
    new_user = is_new_user(user)
    skills = build_progress_skills_list(user)

    completed = 0
    total_lessons = 0
    for s in skills:
        done, total = s["lessons"].split(" / ")
        completed += int(done)
        total_lessons += int(total)
    overall_progress = round(completed * 100 / total_lessons) if total_lessons else 0
    overall_level = max((s["lv"] for s in skills), default=1)

    if new_user:
        ctx = {
            "active": "progress",
            "is_new_user": True,
            "page_subtitle": "Your progress will appear here once you start learning",
            "overall_level": 1,
            "overall_label": "New learner",
            "overall_progress": 0,
            "chips": [
                {"i": "flame", "v": "0", "l": "Streak"},
                {"i": "trophy", "v": "0", "l": "Badges"},
                {"i": "target", "v": "—", "l": "Accuracy"},
            ],
            "skills": skills,
        }
        return render(request, "progress.html", ctx)

    chips = [
        {"i": "flame", "v": str(profile.streak_days), "l": "Streak"},
        {"i": "trophy", "v": str(completed), "l": "Lessons"},
        {"i": "target", "v": format_accuracy(profile.avg_accuracy), "l": "Accuracy"},
    ]
    return render(
        request,
        "progress.html",
        {
            "active": "progress",
            "is_new_user": False,
            "page_subtitle": "Your learning journey, in detail",
            "overall_level": overall_level,
            "overall_label": _level_label(overall_level),
            "overall_progress": overall_progress,
            "skills": skills,
            "chips": chips,
            "badges": range(1, min(7, completed + 1)),
        },
    )


def _level_label(level):
    if level <= 3:
        return "Beginner"
    if level <= 7:
        return "Intermediate"
    if level <= 11:
        return "Advanced"
    return "Fluent"


@login_required
def statistics(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")
    ensure_user_skill_progress(user)
    profile = ensure_profile(user)
    new_user = is_new_user(user)

    if new_user:
        return render(
            request,
            "statistics.html",
            {
                "active": "statistics",
                "is_new_user": True,
                "page_subtitle": "Statistics will populate after your first lessons",
                "cards": [
                    {"l": "Total XP", "v": "0", "d": "No data yet", "trend": "muted"},
                    {"l": "Avg accuracy", "v": "—", "d": "No data yet", "trend": "muted"},
                    {"l": "Study hours", "v": "0h", "d": "No data yet", "trend": "muted"},
                    {"l": "Words learned", "v": "0", "d": "No data yet", "trend": "muted"},
                ],
            },
        )

    skills = build_skills_dashboard_list(user)
    skill_labels = [s["name"] for s in skills if s["slug"] != "speaking"]
    skill_data = [s["progress"] for s in skills if s["slug"] != "speaking"]
    monthly_labels, monthly_data = monthly_xp_data(user)
    pie_labels, pie_data = study_seconds_by_skill_this_month(user)
    acc_labels, acc_data = weekly_accuracy_trend(user)

    if not any(acc_data) and profile.avg_accuracy is not None:
        acc_data = [float(profile.avg_accuracy)] * len(acc_labels)

    ctx = {
        "active": "statistics",
        "is_new_user": False,
        "page_subtitle": "Deep insights into your learning performance",
        "cards": build_statistics_cards(user, profile),
        "monthly_labels": monthly_labels,
        "monthly_data": monthly_data,
        "skill_labels": skill_labels,
        "skill_data": skill_data,
        "pie_labels": pie_labels,
        "pie_data": pie_data,
        "acc_labels": acc_labels,
        "acc_data": acc_data,
    }
    return render(request, "statistics.html", ctx)


@login_required
def profile(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    profile_row = ensure_profile(user)
    new_user = is_new_user(user)
    joined_label = user.created_at.strftime("%b %Y")
    display_name = user.username.replace("_", " ").title()
    initials = user_initials(user.username)

    if new_user:
        tasks = profile_setup_tasks()
        ctx = {
            "active": "profile",
            "is_new_user": True,
            "page_subtitle": "Let's set up your learner profile",
            "username": user.username,
            "email": user.email,
            "display_name": display_name,
            "initials": initials,
            "joined_label": joined_label,
            "setup_tasks": tasks,
            "setup_done": 0,
            "setup_total": len(tasks),
        }
        return render(request, "profile.html", ctx)

    app_ctx = build_app_user_context(user)
    ctx = {
        "active": "profile",
        "is_new_user": False,
        "page_subtitle": "Manage your account information",
        "username": user.username,
        "email": user.email,
        "display_name": display_name,
        "initials": initials,
        "joined_label": joined_label,
        "native_language": profile_row.native_language,
        "app_language": profile_row.app_language,
        "daily_goal_minutes": 20,
        "level": app_ctx["level"],
        "level_label": app_ctx["level_label"],
        "is_pro": False,
    }
    return render(request, "profile.html", ctx)


@login_required
def notifications(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    new_user = is_new_user(user)

    if new_user:
        return render(
            request,
            "notifications.html",
            {
                "active": "notifications",
                "is_new_user": True,
                "page_subtitle": "No updates yet",
                "hints": notification_preview_hints(),
            },
        )

    items = build_notification_items(user)
    unread_count = sum(1 for item in items if item.get("new"))
    return render(
        request,
        "notifications.html",
        {
            "active": "notifications",
            "is_new_user": False,
            "page_subtitle": f"{unread_count} new update{'s' if unread_count != 1 else ''}" if unread_count else "You're all caught up",
            "items": items,
            "unread_count": unread_count,
        },
    )


@login_required
def settings_view(request):
    notif = [
        {"l": "Email notifications", "d": "Receive important updates by email", "on": True},
        {"l": "Study reminders", "d": "Daily push to keep your streak alive", "on": True},
        {"l": "Weekly summary", "d": "A digest of your progress every Sunday", "on": False},
        {"l": "Sounds", "d": "Play interaction and reward sounds", "on": True},
    ]
    region = [
        {"l": "App language", "v": "English"},
        {"l": "Native language", "v": "Spanish"},
        {"l": "Time zone", "v": "(GMT+1) Madrid"},
    ]
    return render(request, "settings.html", {"active": "settings", "notif": notif, "region": region})


@login_required
def premium(request):
    plans = [
        {"name": "Free", "price": 0, "popular": False, "desc": "For casual learners",
         "features": ["5 lessons / day", "Basic listening & reading", "Streak tracking"]},
        {"name": "Pro", "price": 9, "popular": True, "desc": "For serious learners",
         "features": ["Unlimited lessons", "AI writing feedback", "All skill paths", "Advanced statistics", "Priority support"]},
        {"name": "Team", "price": 24, "popular": False, "desc": "For schools & teams",
         "features": ["Everything in Pro", "Team dashboard", "5 seats included", "Custom learning paths", "Dedicated coach"]},
    ]
    for p in plans:
        p["annual_price"] = round(p["price"] * 0.8)
        p["savings"] = round(p["price"] * 0.2 * 12)
    return render(request, "premium.html", {"active": "premium", "plans": plans})
