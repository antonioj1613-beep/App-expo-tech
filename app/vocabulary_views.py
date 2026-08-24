"""Vocabulary review — page view and SM-2 submit API."""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .decorators import login_required
from .stats_service import build_post_practice_payload, build_skill_context, vocabulary_stats_for_user
from .user_helpers import get_logged_in_user
from .vocabulary_service import SKILL_SLUG, submit_vocabulary_review, vocabulary_page_state


def _vocab_lesson_context(lesson) -> dict:
    """
    Deliberately not lesson_service.build_lesson_context(): that helper's
    "Lesson N of Total" and already_completed framing assumes a sequential
    catalog walk where each lesson is shown once. Due-queue review words
    get shown repeatedly by design, so neither concept applies here.
    """
    return {
        "lesson_id": lesson.id,
        "vocab_word": lesson.vocab_word,
        "vocab_ipa": lesson.vocab_ipa,
        "vocab_meaning": lesson.vocab_meaning,
        "vocab_example": lesson.vocab_example,
        "vocab_cefr": lesson.vocab_cefr,
    }


@login_required
def vocabulary(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    skill = build_skill_context(user, SKILL_SLUG)
    page_state = vocabulary_page_state(user)
    lesson = page_state["next_lesson"]
    vocab_stats = vocabulary_stats_for_user(user)

    ctx = {
        "active": "vocabulary",
        "skill": skill,
        "page_state": page_state,
        "vocab_stats": vocab_stats,
        "stats": [
            {"l": "Learned", "v": str(vocab_stats["learned"])},
            {"l": "Mastered", "v": str(vocab_stats["mastered"])},
            {"l": "Review due", "v": str(vocab_stats["review_due"])},
        ],
    }
    if lesson:
        ctx.update(_vocab_lesson_context(lesson))
    return render(request, "vocabulary.html", ctx)


@login_required
@require_POST
def vocabulary_submit(request):
    user = get_logged_in_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated."}, status=401)

    try:
        lesson_id = int(request.POST.get("lesson_id", "0"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid submission."}, status=400)

    correct = request.POST.get("correct") == "1"

    result = submit_vocabulary_review(user, lesson_id, correct)
    if result.get("error"):
        return JsonResponse({"error": result["error"]}, status=result.get("status", 400))

    payload = build_post_practice_payload(
        user,
        skill_slug=SKILL_SLUG,
        xp_earned=result["xp_earned"],
        accuracy_score=100.0 if correct else 0.0,
    )
    payload.update(
        {
            "correct": result["correct"],
            "is_first_review": result["is_first_review"],
            "next_review_date": result["next_review_date"],
            "interval_days": result["interval_days"],
            "mastered": result["mastered"],
            "has_next": result["has_next"],
        }
    )
    return JsonResponse(payload)
