"""Speaking tutor replies — Ollama when available, smart fallbacks otherwise."""

from __future__ import annotations

import json
import os
import random

import httpx

TUTOR_PROMPTS = {
    "Miles": (
        "You are Miles, a friendly male English speaking tutor. "
        "Keep every reply to 1-2 short spoken sentences. Ask one follow-up question."
    ),
    "Maya": (
        "You are Maya, a warm female English speaking tutor. "
        "Keep every reply to 1-2 short spoken sentences. Ask one follow-up question."
    ),
}

STARTER_QUESTIONS = {
    "Miles": [
        "Hi, I'm Miles. What did you do today?",
        "Let's practice speaking. Tell me about your favorite hobby.",
        "Nice to meet you. What's something you're excited about this week?",
    ],
    "Maya": [
        "Hi, I'm Maya. How are you feeling today?",
        "Let's warm up — describe your morning in a few sentences.",
        "Great to see you. What's a place you'd love to visit and why?",
    ],
}

FOLLOW_UPS = [
    "That's interesting. Can you tell me a bit more?",
    "Nice answer. Why do you feel that way?",
    "Good job. Can you give me a specific example?",
    "I like that. What happened next?",
    "Well said. How would you explain that to a friend?",
]


def ollama_available() -> bool:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        response = httpx.get(f"{url}/api/tags", timeout=2.0)
        return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _ollama_reply(character: str, user_message: str, history: list[dict]) -> str | None:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    messages = [{"role": "system", "content": TUTOR_PROMPTS.get(character, TUTOR_PROMPTS["Miles"])}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_message})

    try:
        response = httpx.post(
            f"{url}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=45.0,
        )
        if response.status_code != 200:
            return None
        content = response.json().get("message", {}).get("content", "").strip()
        return content or None
    except (httpx.HTTPError, OSError, json.JSONDecodeError, KeyError):
        return None


def _fallback_reply(user_message: str) -> str:
    text = user_message.strip()
    if not text:
        return "I didn't catch that. Could you try again?"
    if len(text.split()) < 4:
        return random.choice(FOLLOW_UPS)
    return (
        f"You said: \"{text[:120]}\". "
        f"{random.choice(FOLLOW_UPS)}"
    )


def starter_question(character: str) -> str:
    choices = STARTER_QUESTIONS.get(character, STARTER_QUESTIONS["Miles"])
    return random.choice(choices)


def tutor_reply(character: str, user_message: str, history: list[dict]) -> dict:
    character = character if character in TUTOR_PROMPTS else "Miles"
    reply = _ollama_reply(character, user_message, history)
    engine = "ollama" if reply else "builtin"
    if not reply:
        reply = _fallback_reply(user_message)
    return {"reply": reply, "engine": engine}
