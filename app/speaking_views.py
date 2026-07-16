"""Speaking practice — browser voice chat with a local AI tutor."""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .decorators import login_required
from .models import SpeakingSession
from .speaking_stt import model_ready, transcribe_wav, vosk_installed
from .speaking_tutor import MAX_HISTORY_TURNS, learner_global_level, ollama_available, starter_question, tutor_reply
from .stats_service import build_post_session_payload, build_skill_context, finalize_speaking_session
from .user_helpers import get_logged_in_user


def _clean_transcript(raw: list) -> list[dict]:
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def _user_global_level(user) -> int:
    profile = getattr(user, "profile", None)
    total_xp = profile.total_xp if profile else 0
    return learner_global_level(total_xp)


def _get_owned_session(user, session_id: str | None) -> SpeakingSession | None:
    if not session_id:
        return None
    try:
        pk = int(session_id)
    except (TypeError, ValueError):
        return None
    return SpeakingSession.objects.filter(pk=pk, user=user).first()


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
    user = get_logged_in_user(request)
    character = request.POST.get("character", "Miles")
    if character not in ("Miles", "Maya"):
        character = "Miles"

    question = starter_question(character)

    # Remove abandoned sessions that never received a learner turn.
    for old in SpeakingSession.objects.filter(user=user, xp_earned=0):
        turns = _clean_transcript(old.transcript)
        if not any(t["role"] == "user" for t in turns):
            old.delete()

    session = SpeakingSession.objects.create(
        user=user,
        tutor=character,
        transcript=[{"role": "assistant", "content": question}],
    )

    return JsonResponse(
        {
            "question": question,
            "session_id": session.id,
            "engine": "ollama" if ollama_available() else "builtin",
        }
    )


@login_required
@require_POST
def speaking_chat(request):
    user = get_logged_in_user(request)
    character = request.POST.get("character", "Miles")
    message = request.POST.get("message", "").strip()
    session_id = request.POST.get("session_id", "")

    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    session = _get_owned_session(user, session_id)
    if not session:
        return JsonResponse({"error": "Speaking session not found."}, status=400)

    transcript = _clean_transcript(session.transcript)
    history = transcript[-MAX_HISTORY_TURNS:]

    global_level = _user_global_level(user)
    result = tutor_reply(character, message, history, global_level=global_level)

    transcript.append({"role": "user", "content": message})
    transcript.append({"role": "assistant", "content": result["reply"]})
    session.transcript = transcript
    session.save(update_fields=["transcript"])

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
    """Finalize a voice session and update profile / skill progress."""
    user = get_logged_in_user(request)
    if not user:
        return JsonResponse({"error": "Not authenticated."}, status=401)

    session_id = request.POST.get("session_id", "")
    try:
        duration_seconds = int(request.POST.get("duration_seconds", "0"))
    except (TypeError, ValueError):
        duration_seconds = 0

    session = _get_owned_session(user, session_id)
    if not session:
        return JsonResponse({"error": "Speaking session not found."}, status=400)

    if session.xp_earned > 0:
        return JsonResponse(build_post_session_payload(user, session))

    cleaned = _clean_transcript(session.transcript)
    user_turns = [t for t in cleaned if t["role"] == "user"]
    if not user_turns:
        session.delete()
        return JsonResponse({"error": "No user messages to save."}, status=400)

    session.transcript = cleaned
    session.save(update_fields=["transcript"])
    session = finalize_speaking_session(session, duration_seconds=duration_seconds)
    return JsonResponse(build_post_session_payload(user, session))
