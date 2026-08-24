"""Writing practice — lesson page and submit API.

Scoring is a temporary word-count heuristic. Real AI-graded feedback (grammar,
clarity, tone) is planned — see gamification.compute_writing_lesson_xp, which
already expects a 0-100 rubric_score from whatever scorer sits here.
"""

from __future__ import annotations

from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .decorators import login_required
from .gamification import compute_writing_lesson_xp
from .lesson_service import LESSON_DURATION_SECONDS, build_lesson_context, get_next_lesson_for_user, get_skill_page_state
from .models import SkillLesson, UserSkillLessonCompletion
from .stats_service import build_post_practice_payload, build_skill_context, record_practice_session
from .user_helpers import get_logged_in_user

SKILL_SLUG = "writing"


def _placeholder_score(word_count: int, min_words: int | None, max_words: int | None) -> int:
    """Word-count based stand-in until real AI grading lands."""
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
    return "Nice work — your answer meets the length target. Full AI grammar and tone feedback is coming soon."


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

    already = UserSkillLessonCompletion.objects.filter(user=user, lesson=lesson).exists()
    rubric_score = _placeholder_score(word_count, lesson.min_words, lesson.max_words)
    feedback = _placeholder_feedback(word_count, lesson.min_words, lesson.max_words)

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
        }
    )
    return JsonResponse(payload)
