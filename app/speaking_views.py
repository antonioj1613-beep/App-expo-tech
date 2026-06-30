"""Speaking practice — browser voice chat with a local AI tutor."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .decorators import login_required
from .speaking_stt import model_ready, transcribe_wav, vosk_installed
from .speaking_tutor import ollama_available, starter_question, tutor_reply
from .stats_service import build_skill_context, record_speaking_session
from .user_helpers import ensure_profile, get_logged_in_user


def speaking_page_context(request) -> dict:
    user = get_logged_in_user(request)
    skill = build_skill_context(user, "speaking") if user else {}
    return {
        "ollama_ready": ollama_available(),
        "stt_ready": vosk_installed() and model_ready(),
        "skill": skill,
    }


@login_required
def speaking(request):
    user = get_logged_in_user(request)
    ctx = speaking_page_context(request)
    skill = ctx.get("skill", {})
    return render(
        request,
        "speaking.html",
        {
            "active": "speaking",
            "page_subtitle": skill.get("subtitle", "Voice conversation practice with Miles & Maya"),
            **ctx,
        },
    )


@login_required
@require_POST
def speaking_start(request):
    character = request.POST.get("character", "Miles")
    if character not in ("Miles", "Maya"):
        character = "Miles"
    return JsonResponse(
        {
            "question": starter_question(character),
            "engine": "ollama" if ollama_available() else "builtin",
        }
    )


@login_required
@require_POST
def speaking_chat(request):
    character = request.POST.get("character", "Miles")
    message = request.POST.get("message", "").strip()
    history_raw = request.POST.get("history", "[]")

    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    try:
        history = json.loads(history_raw)
        if not isinstance(history, list):
            history = []
    except json.JSONDecodeError:
        history = []

    cleaned_history = []
    for item in history[-8:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            cleaned_history.append({"role": role, "content": content})

    result = tutor_reply(character, message, cleaned_history)
    return JsonResponse(result)


@login_required
@require_POST
def speaking_transcribe(request):
    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "No audio received."}, status=400)

    try:
        transcript = transcribe_wav(audio.read())
    except Exception as exc:
        return JsonResponse({"error": f"Could not transcribe audio: {exc}"}, status=503)

    if not transcript:
        return JsonResponse({"error": "No speech detected. Try speaking louder or closer to the mic."}, status=400)

    return JsonResponse({"transcript": transcript})


@login_required
@require_POST
def speaking_end(request):
    """Persist a completed voice session and update profile / skill progress."""
    user = get_logged_in_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated."}, status=401)

    character = request.POST.get("character", "Miles")
    history_raw = request.POST.get("history", "[]")
    try:
        duration_seconds = int(request.POST.get("duration_seconds", "0"))
    except (TypeError, ValueError):
        duration_seconds = 0

    try:
        transcript = json.loads(history_raw)
        if not isinstance(transcript, list):
            transcript = []
    except json.JSONDecodeError:
        transcript = []

    cleaned = []
    for item in transcript:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})

    user_turns = [t for t in cleaned if t["role"] == "user"]
    if not user_turns:
        return JsonResponse({"error": "No user messages to save."}, status=400)

    session = record_speaking_session(
        user,
        tutor=character,
        transcript=cleaned,
        duration_seconds=duration_seconds,
    )
    profile = ensure_profile(user)
    profile.refresh_from_db()
    return JsonResponse(
        {
            "ok": True,
            "session_id": session.id,
            "xp_earned": session.xp_earned,
            "accuracy_score": float(session.accuracy_score) if session.accuracy_score is not None else None,
            "total_xp": profile.total_xp,
        }
    )
