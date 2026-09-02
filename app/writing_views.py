"""Writing practice — lesson page and submit API.

Submit-time scoring calls writing_feedback.grade_writing_submission() for a
real AI rubric score, error extraction, and recommendations. On any Gemini
failure or timeout, this falls back to the original word-count heuristic
below — kept deliberately, not deleted, matching Speaking's
_fallback_reply() precedent for graceful degradation.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .decorators import login_required
from .gamification import compute_writing_lesson_xp
from .lesson_service import LESSON_DURATION_SECONDS, build_lesson_context, get_next_lesson_for_user, get_skill_page_state
from .models import SkillLesson, UserSkillLessonCompletion, UserSkillProgress
from .stats_service import build_post_practice_payload, build_skill_context, record_practice_session
from .user_helpers import get_logged_in_user
from .writing_feedback import build_weak_points_summary, grade_writing_submission, record_writing_errors

SKILL_SLUG = "writing"


def _placeholder_score(word_count: int, min_words: int | None, max_words: int | None) -> int:
    """Word-count based stand-in — used only when the AI grading call fails."""
    if not min_words:
        return 75 if word_count > 0 else 0
    if word_count < min_words:
        return max(10, round(50 * word_count / min_words))
    if max_words and word_count > max_words:
        return 70
    return 85


def _placeholder_feedback(word_count: int, min_words: int | None, max_words: int | None) -> str:
    if min_words and word_count < min_words:
        return f"You wrote {word_count} word{'s' if word_count != 1 else ''} — try to reach at least {min_words} for a complete answer."
    if max_words and word_count > max_words:
        return f"Good effort — you're a bit past the {max_words}-word target, but your answer is complete."
    return "Nice work — your answer meets the length target."


def _writing_cefr_level(user) -> str | None:
    """Writing's own per-skill CEFR level — same authority as Speaking's
    _speaking_cefr_level in speaking_views.py, used to calibrate AI grading
    tone rather than the account-global derived level."""
    progress = UserSkillProgress.objects.filter(user=user, skill__slug=SKILL_SLUG).first()
    return progress.cefr_level if progress else None


@login_required
def writing(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    skill = build_skill_context(user, SKILL_SLUG)
    page_state = get_skill_page_state(user, SKILL_SLUG)
    lesson = page_state["next_lesson"]
    ctx = {
        "active": "writing",
        "skill": skill,
        "page_state": page_state,
    }
    if lesson:
        ctx.update(build_lesson_context(lesson, user, SKILL_SLUG))
    return render(request, "writing.html", ctx)


@login_required
@require_POST
def writing_submit(request):
    user = get_logged_in_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated."}, status=401)

    try:
        lesson_id = int(request.POST.get("lesson_id", "0"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid submission."}, status=400)

    essay = request.POST.get("essay", "").strip()
    if not essay:
        return JsonResponse({"error": "Please write something before submitting."}, status=400)

    try:
        lesson = SkillLesson.objects.select_related("skill").get(pk=lesson_id, skill__slug=SKILL_SLUG)
    except SkillLesson.DoesNotExist:
        return JsonResponse({"error": "Lesson not found."}, status=404)

    expected = get_next_lesson_for_user(user, SKILL_SLUG)
    if not expected or expected.id != lesson.id:
        return JsonResponse({"error": "This is not your current lesson."}, status=400)

    word_count = len(essay.split())
    if lesson.min_words and word_count < lesson.min_words:
        return JsonResponse(
            {"error": f"Write at least {lesson.min_words} words (you wrote {word_count})."},
            status=400,
        )

    SkillLesson.objects.filter(pk=lesson.pk).update(times_practiced=F("times_practiced") + 1)

    already = UserSkillLessonCompletion.objects.filter(user=user, lesson=lesson).exists()

    ai_result = grade_writing_submission(
        user=user,
        essay=essay,
        prompt_text=lesson.writing_prompt,
        min_words=lesson.min_words,
        max_words=lesson.max_words,
        cefr_level=_writing_cefr_level(user),
    )
    if ai_result:
        rubric_score = ai_result["rubric_score"]
        feedback = ai_result["feedback_summary"]
        errors = ai_result["errors"]
        recommendations = ai_result["recommendations"]
    else:
        rubric_score = _placeholder_score(word_count, lesson.min_words, lesson.max_words)
        feedback = _placeholder_feedback(word_count, lesson.min_words, lesson.max_words)
        errors = []
        recommendations = []

    xp_earned = 0
    if not already:
        xp_earned = compute_writing_lesson_xp(rubric_score)
        record_practice_session(
            user,
            skill_slug=SKILL_SLUG,
            xp_earned=xp_earned,
            accuracy_score=Decimal(rubric_score),
            duration_seconds=LESSON_DURATION_SECONDS,
            lessons_completed=1,
            lesson_level=lesson.level,
        )
        UserSkillLessonCompletion.objects.create(user=user, lesson=lesson, xp_earned=xp_earned)
        record_writing_errors(user, errors)

    next_lesson = get_next_lesson_for_user(user, SKILL_SLUG)
    payload = build_post_practice_payload(
        user,
        skill_slug=SKILL_SLUG,
        xp_earned=xp_earned,
        accuracy_score=float(rubric_score),
    )
    payload.update(
        {
            "feedback": feedback,
            "rubric_score": rubric_score,
            "word_count": word_count,
            "already_completed": already,
            "has_next_lesson": next_lesson is not None,
            "errors": errors,
            "recommendations": recommendations,
            "weak_points": build_weak_points_summary(user),
        }
    )
    return JsonResponse(payload)
