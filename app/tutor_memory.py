"""
Tutor persistent error memory — Phase 3.

Post-session extraction only (see Phase 3 design doc): a dedicated Ollama
call runs once when a Speaking session ends, over the whole transcript, not
inline during the live conversation. Inline extraction would either add a
second Ollama round-trip to every conversational turn (direct latency cost
while the student is mid-chat) or force one call to do two different jobs
at once (natural reply + structured classification), which small local
models handle less reliably than single-purpose prompts. Post-session
extraction also sees the complete transcript at once, which is the only
vantage point "recurring within this session" is even detectable from.

This module owns extraction (Ollama call + parsing), persistence
(get_or_create/reinforce), and the injection query — kept separate from
speaking_tutor.py (conversational prompt assembly) and stats_service.py
(XP/accuracy/levels), matching the existing one-concern-per-file
convention (vocabulary_service.py, reading_service.py).
"""

from __future__ import annotations

import json
import os
from datetime import timedelta

import httpx
from django.utils import timezone

from .gamification import ERROR_CATEGORIES, ERROR_CATEGORY_KEYS
from .models import Skill, TutorErrorPattern, User

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
EXTRACTION_MIN_LEARNER_TURNS = 2  # below this, nothing "recurring" is observable
EXTRACTION_TIMEOUT_SECONDS = 15.0  # shorter than the 45s conversational timeout —
# this runs while the student is on the results screen, not mid-chat, but it
# still shouldn't hang the response indefinitely.
EXAMPLE_NOTE_MAX_LENGTH = 200  # defensive cap even if the model ignores the length hint

_CATEGORY_LIST_FOR_PROMPT = "\n".join(f"- {key}: {label}" for key, label in ERROR_CATEGORIES)

EXTRACTION_SYSTEM_PROMPT = f"""
You are analyzing a transcript of an English learner practicing spoken English with an AI tutor. Your only job is to identify recurring language error patterns in the LEARNER's turns. Ignore the tutor's turns entirely.

Classify each distinct error you notice into EXACTLY ONE of these categories (use the category key exactly as written, do not invent new categories):
{_CATEGORY_LIST_FOR_PROMPT}

Rules:
- Only include a category if you see a real, clear instance of that error type in the learner's own words.
- For each category you include, give ONE short example (under 15 words) quoting or paraphrasing what the learner said.
- A single clear instance is enough to report — you do not need to see it repeated within this one transcript. Persistent tracking across sessions is handled separately from your output.
- If you see no clear errors, output an empty list.

Output ONLY valid JSON, no markdown fences, no other text, in exactly this shape:
[{{"category": "th_sound", "example": "said 'tink' instead of 'think'"}}]
""".strip()


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()


def _extract_via_ollama(learner_turns: list[str]) -> list[dict]:
    """Returns [] on any failure (Ollama down, timeout, bad JSON) — never raises."""
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    transcript_text = "\n".join(f"- {turn}" for turn in learner_turns)

    try:
        response = httpx.post(
            f"{url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": transcript_text},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 300},
            },
            timeout=EXTRACTION_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return []
        content = response.json().get("message", {}).get("content", "")
        parsed = json.loads(_strip_code_fences(content))
    except (httpx.HTTPError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return []

    if not isinstance(parsed, list):
        return []

    detected = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        example = str(item.get("example", "")).strip()
        if category in ERROR_CATEGORY_KEYS:
            detected.append({"category": category, "example": example})
    return detected


def record_error_pattern(user: User, skill_slug: str, category: str, example_note: str) -> TutorErrorPattern | None:
    skill = Skill.objects.filter(slug=skill_slug).first()
    if not skill or category not in ERROR_CATEGORY_KEYS:
        return None

    trimmed_note = example_note[:EXAMPLE_NOTE_MAX_LENGTH]
    pattern, created = TutorErrorPattern.objects.get_or_create(
        user=user,
        skill=skill,
        category=category,
        defaults={"example_note": trimmed_note},
    )
    if not created:
        pattern.occurrence_count += 1
        pattern.example_note = trimmed_note
        pattern.resolved_at = None
        pattern.save(update_fields=["occurrence_count", "example_note", "resolved_at", "last_detected_at"])
    return pattern


def run_error_extraction(user: User, skill_slug: str, transcript: list[dict]) -> None:
    """Best-effort — never raises. Call after a session is finalized; a
    failure here must not affect session finalization itself."""
    learner_turns = [
        str(turn.get("content", "")).strip()
        for turn in transcript
        if isinstance(turn, dict) and turn.get("role") == "user" and str(turn.get("content", "")).strip()
    ]
    if len(learner_turns) < EXTRACTION_MIN_LEARNER_TURNS:
        return

    for item in _extract_via_ollama(learner_turns):
        record_error_pattern(user, skill_slug, item["category"], item["example"])


# ---------------------------------------------------------------------------
# Injection (used by speaking_tutor.build_system_prompt via speaking_views)
# ---------------------------------------------------------------------------
INJECTION_TOP_N = 3
INJECTION_MIN_OCCURRENCE = 2  # a single-session detection isn't "recurring" yet
INJECTION_RECENCY_DAYS = 90  # stale patterns stop being shown, not deleted


def get_top_error_patterns(user: User, skill_slug: str, limit: int = INJECTION_TOP_N) -> list[TutorErrorPattern]:
    cutoff = timezone.now() - timedelta(days=INJECTION_RECENCY_DAYS)
    return list(
        TutorErrorPattern.objects.filter(
            user=user,
            skill__slug=skill_slug,
            occurrence_count__gte=INJECTION_MIN_OCCURRENCE,
            last_detected_at__gte=cutoff,
            resolved_at__isnull=True,
        ).order_by("-occurrence_count", "-last_detected_at")[:limit]
    )


def format_error_context_for_prompt(patterns: list[TutorErrorPattern]) -> str:
    """Degrades to "" (no header, no section) when there's nothing to show —
    most students, especially early on, will have zero qualifying patterns."""
    if not patterns:
        return ""
    items = "; ".join(f"{p.get_category_display()} ({p.occurrence_count}x)" for p in patterns)
    return (
        "KNOWN RECURRING ERRORS for this learner — prioritize correcting these "
        f"over other minor slips when they occur: {items}."
    )
