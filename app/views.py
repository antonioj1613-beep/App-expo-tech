from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
import sqlite3
from pathlib import Path

from .auth_utils import check_password, hash_password
from .decorators import login_required
from .speaking_views import speaking_page_context
from .models import Skill, User, UserSkillProgress
from .stats_service import (
    build_progress_skills_list,
    build_skill_context,
    build_skills_dashboard_list,
    ensure_user_skill_progress,
    format_accuracy,
    format_number,
    format_study_hours,
)
from .user_helpers import ensure_profile, get_logged_in_user, is_new_user, time_greeting


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


def login_view(request):
    if request.session.get("user_id"):
        return redirect("dashboard")

    ctx = _auth_context("login")

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
        return redirect("dashboard")

    ctx = _auth_context("register")

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
def _profile_stats_cards(profile):
    return [
        {"label": "Total XP", "value": format_number(profile.total_xp), "suffix": "", "icon": "zap", "color": "text-primary"},
        {"label": "Avg accuracy", "value": format_accuracy(profile.avg_accuracy).replace("%", ""), "suffix": "%" if profile.avg_accuracy is not None else "", "icon": "target", "color": "text-success"},
        {"label": "Study hours", "value": format_study_hours(profile.study_hours), "suffix": "", "icon": "clock", "color": "text-accent"},
        {"label": "Words learned", "value": format_number(profile.words_learned), "suffix": "", "icon": "book-open", "color": "text-warning"},
    ]


@login_required
def dashboard(request):
    user = get_logged_in_user(request)
    if not user:
        request.session.flush()
        return redirect("login")

    ensure_user_skill_progress(user)
    profile = ensure_profile(user)
    new_user = is_new_user(user)
    name = user.username.replace("_", " ").title()

    if new_user:
        ctx = {
            "active": "dashboard",
            "is_new_user": True,
            "page_title": f"{time_greeting()}, {name.split()[0]}",
            "page_subtitle": "Let's take your first steps to personalize your English.",
            "stats": [
                {"label": "Total XP", "value": "0", "suffix": "", "icon": "zap", "color": "text-primary"},
                {"label": "Avg accuracy", "value": "—", "suffix": "", "icon": "target", "color": "text-success"},
                {"label": "Study hours", "value": "0h", "suffix": "", "icon": "clock", "color": "text-accent"},
                {"label": "Words learned", "value": "0", "suffix": "", "icon": "book-open", "color": "text-warning"},
            ],
            "setup_tasks": [
                {
                    "title": "Take the level test",
                    "description": "Find your starting point so lessons match your level.",
                    "url": "levels",
                    "button": "Start",
                    "done": False,
                },
                {
                    "title": "Choose your goal",
                    "description": "Tell us why you're learning — work, travel, exams, or fun.",
                    "url": "settings",
                    "button": "Choose",
                    "done": False,
                },
                {
                    "title": "Your first lesson",
                    "description": "A short lesson to get a feel for how Learning Skills works.",
                    "url": "listening",
                    "button": "Go",
                    "done": False,
                },
            ],
            "setup_done": 0,
            "setup_total": 3,
            "starter_lessons": [
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
            ],
        }
        return render(request, "dashboard.html", ctx)

    skills = build_skills_dashboard_list(user)
    lessons_done = sum(
        UserSkillProgress.objects.filter(user=user).values_list("lessons_completed", flat=True)
    )

    ctx = {
        "active": "dashboard",
        "is_new_user": False,
        "page_title": "Dashboard",
        "page_subtitle": f"Welcome back, {name.split()[0]} — let's keep the streak alive 🔥",
        "stats": _profile_stats_cards(profile),
        "skills": skills,
        "lessons_done": lessons_done,
        "week_xp_total": sum(_weekly_xp_data(user)),
        "week_data": _weekly_xp_data(user),
        "week_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "streak_days": profile.streak_days,
    }
    return render(request, "dashboard.html", ctx)


def _weekly_xp_data(user):
    """XP earned per weekday (Mon–Sun) for the current calendar week."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import SpeakingSession

    today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    buckets = [0] * 7
    sessions = SpeakingSession.objects.filter(
        user=user,
        created_at__date__gte=monday,
        created_at__date__lte=monday + timedelta(days=6),
    )
    for session in sessions:
        day_index = (session.created_at.date() - monday).days
        if 0 <= day_index < 7:
            buckets[day_index] += session.xp_earned
    return buckets


@login_required
def levels(request):
    user = get_logged_in_user(request)
    items = []
    for n in range(1, 16):
        items.append({"n": n, "unlocked": n <= 2, "completed": n == 1})

    skill_rows = Skill.objects.all()
    skills = []
    for skill in skill_rows:
        meta = {
            "listening": ("headphones", "Train your ear with real-world audio", "listening"),
            "reading": ("book-open", "Build comprehension from texts at your level", "reading"),
            "writing": ("pen-line", "Practice writing with instant AI feedback", "writing"),
            "vocabulary": ("graduation-cap", "Grow your word bank with smart repetition", "vocabulary"),
            "speaking": ("mic", "Voice conversation practice with AI tutors Miles & Maya", "speaking"),
        }.get(skill.slug, ("layers", "", skill.slug))
        lessons_label = (
            "Voice chat" if skill.slug == "speaking" else f"{skill.total_lessons}+"
        )
        skills.append(
            {
                "id": skill.slug,
                "name": skill.name,
                "icon": meta[0],
                "tagline": meta[1],
                "lessons": lessons_label,
                "url": meta[2],
            }
        )

    return render(
        request,
        "levels.html",
        {
            "active": "levels",
            "levels": items,
            "skills": skills,
            **speaking_page_context(request),
        },
    )


@login_required
def listening(request):
    user = get_logged_in_user(request)
    skill = build_skill_context(user, "listening")
    options = [
        "A natural disaster recovery",
        "A new remote work policy",
        "A quarterly sales report",
        "An employee feedback session",
    ]
    return render(request, "listening.html", {"active": "listening", "options": options, "skill": skill})


@login_required
def reading(request):
    user = get_logged_in_user(request)
    skill = build_skill_context(user, "reading")
    passage = """From: Sarah Chen, HR Director
To: All Employees
Subject: New Remote Work Guidelines

Dear team,

Following last quarter's feedback, we are rolling out an updated remote work policy that takes effect on March 1st. Each team will be required to coordinate at least two in-office days per week, with the specific days chosen by the team lead in collaboration with each member.

We believe this hybrid model best balances flexibility with collaboration. Managers will host a kickoff session next week to discuss expectations and answer your questions.

Best,
Sarah"""
    options = [
        "To request feedback on employees",
        "To notify employees of a new remote work policy",
        "To introduce a new supervisor",
        "To announce a salary adjustment",
    ]
    return render(request, "reading.html", {"active": "reading", "passage": passage, "options": options, "selected": 1, "skill": skill})


@login_required
def writing(request):
    user = get_logged_in_user(request)
    skill = build_skill_context(user, "writing")
    metrics = [
        {"label": "Grammar", "score": 92, "c": "text-success"},
        {"label": "Clarity", "score": 84, "c": "text-primary"},
        {"label": "Tone", "score": 76, "c": "text-accent"},
        {"label": "Vocabulary", "score": 88, "c": "text-success"},
    ]
    return render(request, "writing.html", {"active": "writing", "metrics": metrics, "skill": skill})


@login_required
def vocabulary(request):
    user = get_logged_in_user(request)
    profile = ensure_profile(user)
    skill = build_skill_context(user, "vocabulary")
    words = [
        {"w": "Ephemeral", "ipa": "/ɪˈfɛm(ə)rəl/", "meaning": "Lasting for a very short time.", "ex": "The beauty of the sunset is ephemeral.", "lv": "C1", "mastered": True},
        {"w": "Resilient", "ipa": "/rɪˈzɪlɪənt/", "meaning": "Able to recover quickly from difficulty.", "ex": "She remained resilient throughout the project.", "lv": "B2", "mastered": True},
        {"w": "Pragmatic", "ipa": "/præɡˈmætɪk/", "meaning": "Dealing with things sensibly and realistically.", "ex": "A pragmatic approach works best.", "lv": "C1", "mastered": False},
        {"w": "Ubiquitous", "ipa": "/juːˈbɪkwɪtəs/", "meaning": "Present, appearing, or found everywhere.", "ex": "Smartphones are ubiquitous today.", "lv": "C2", "mastered": False},
        {"w": "Candid", "ipa": "/ˈkændɪd/", "meaning": "Truthful and straightforward.", "ex": "I appreciate your candid feedback.", "lv": "B2", "mastered": False},
        {"w": "Meticulous", "ipa": "/mɪˈtɪkjʊləs/", "meaning": "Showing great attention to detail.", "ex": "He is meticulous in his work.", "lv": "C1", "mastered": True},
    ]
    stats = [
        {"l": "Learned", "v": str(profile.words_learned)},
        {"l": "Mastered", "v": "0"},
        {"l": "Review due", "v": "0"},
    ]
    return render(
        request,
        "vocabulary.html",
        {"active": "vocabulary", "words": words, "stats": stats, "skill": skill},
    )


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
    pie_data = skill_data or [0, 0, 0, 0]

    ctx = {
        "active": "statistics",
        "is_new_user": False,
        "page_subtitle": "Deep insights into your learning performance",
        "cards": [
            {"l": "Total XP", "v": format_number(profile.total_xp), "d": "From all practice", "trend": "success"},
            {"l": "Avg accuracy", "v": format_accuracy(profile.avg_accuracy), "d": "From scored sessions", "trend": "success"},
            {"l": "Study hours", "v": format_study_hours(profile.study_hours), "d": "Time practicing", "trend": "success"},
            {"l": "Words learned", "v": format_number(profile.words_learned), "d": "Vocabulary progress", "trend": "primary"},
        ],
        "monthly_labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"],
        "monthly_data": [profile.total_xp // 8] * 8,
        "skill_labels": skill_labels,
        "skill_data": skill_data,
        "pie_labels": skill_labels,
        "pie_data": pie_data,
        "acc_labels": ["W1", "W2", "W3", "W4", "W5", "W6", "W7"],
        "acc_data": [float(profile.avg_accuracy or 0)] * 7,
    }
    return render(request, "statistics.html", ctx)


@login_required
def profile(request):
    return render(request, "profile.html", {"active": "profile"})


@login_required
def notifications(request):
    items = [
        {"icon": "trophy", "t": "You earned the 'Perfect Week' badge!", "d": "2h ago", "new": True, "c": "text-warning bg-warning/15"},
        {"icon": "flame", "t": "12-day streak — keep it going!", "d": "5h ago", "new": True, "c": "text-warning bg-warning/15"},
        {"icon": "sparkles", "t": "New lesson available: 'Business Emails'", "d": "Yesterday", "new": True, "c": "text-primary bg-primary/15"},
        {"icon": "message-square", "t": "Your writing was reviewed by AI tutor", "d": "2d ago", "new": False, "c": "text-accent bg-accent/15"},
        {"icon": "trophy", "t": "Completed Listening Level 7", "d": "3d ago", "new": False, "c": "text-success bg-success/15"},
        {"icon": "bell", "t": "Weekly summary is ready", "d": "Last week", "new": False, "c": "text-muted-foreground bg-muted"},
    ]
    return render(request, "notifications.html", {"active": "notifications", "items": items})


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
