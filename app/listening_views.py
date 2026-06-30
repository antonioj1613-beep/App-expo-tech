"""Listening comprehension — lesson page and submit API."""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .decorators import login_required
from .lesson_service import build_lesson_context, get_skill_page_state, submit_quiz_answer
from .stats_service import build_post_practice_payload, build_skill_context
from .user_helpers import get_logged_in_user


@login_required
def listening(request):
    user = get_logged_in_user(request)
    if not user:
        return redirect("login")

    skill = build_skill_context(user, "listening")
    page_state = get_skill_page_state(user, "listening")
    lesson = page_state["next_lesson"]

    if page_state["coming_soon"]:
        return render(
            request,
            "listening.html",
            {
                "active": "listening",
                "skill": skill,
                "page_state": page_state,
            },
        )

    ctx = build_lesson_context(lesson, user, "listening")
    return render(
        request,
        "listening.html",
        {
            "active": "listening",
            "page_state": page_state,
            **ctx,
        },
    )


@login_required
@require_POST
def listening_submit(request):
    user = get_logged_in_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated."}, status=401)

    try:
        lesson_id = int(request.POST.get("lesson_id", "0"))
        selected_index = int(request.POST.get("selected_index", "-1"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid submission."}, status=400)

    result = submit_quiz_answer(user, "listening", lesson_id, selected_index)
    if result.get("error"):
        return JsonResponse({"error": result["error"]}, status=result.get("status", 400))

    accuracy = float(result["accuracy"]) if result.get("accuracy") is not None else None
    payload = build_post_practice_payload(
        user,
        skill_slug="listening",
        xp_earned=result["xp_earned"],
        accuracy_score=accuracy,
    )
    payload.update(
        {
            "was_correct": result["was_correct"],
            "correct_index": result["correct_index"],
            "already_completed": result["already_completed"],
            "has_next_lesson": result["has_next_lesson"],
        }
    )
    return JsonResponse(payload)
