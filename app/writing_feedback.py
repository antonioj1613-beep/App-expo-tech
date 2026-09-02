"""
Writing submit-time AI grading — writing feature.

One combined Gemini call per submission (Google AI Studio free tier —
generateContent, not Ollama), returning a holistic rubric score, prose
feedback, detected error patterns, and higher-level recommendations in a
single structured JSON response. Combined into one call rather than split
like Speaking's live-reply/post-session-extraction split, because a
Writing submission happens once per lesson attempt — there's no "keep the
hot path fast" pressure the way Speaking's live chat turns have, so
splitting would only multiply the worst-case wait for no benefit.

Speaking (speaking_tutor.py, tutor_memory.py) intentionally still uses
Ollama, unchanged — this module is the only one that switched providers.

On any failure (missing/invalid GEMINI_API_KEY, Gemini unreachable,
timeout, rate limit, bad JSON, missing required fields) this returns
None — the caller (writing_views.writing_submit) falls back to the
pre-existing word-count placeholder, exactly like Speaking falls back to
_fallback_reply() when Ollama is unavailable.

Kept separate from tutor_memory.py (which stays skill-agnostic — record
storage + injection query only) and doesn't extend
tutor_memory.run_error_extraction(), whose transcript-shaped input and
Speaking-specific prompt don't fit a single essay submission.
"""

from __future__ import annotations

import json
import os
import time

import httpx

from .gamification import SKILL_ERROR_CATEGORIES
from .tutor_memory import format_error_context_for_prompt, get_top_error_patterns, record_error_pattern

GRADING_TIMEOUT_SECONDS = 20.0  # a submit-time call the student is waiting on,
# same graceful-degradation shape as Speaking's post-session extraction,
# just a shorter budget since nothing else in the response depends on it.

# 503 on the free tier means "Gemini is overloaded right now" -- transient,
# not a real failure, and worth a couple quick retries before giving up on
# real AI feedback for the submission. Every other failure (4xx, other 5xx,
# timeout, connection error, bad JSON) is left alone and still fails straight
# to the placeholder, same as before -- those aren't overload signals.
GEMINI_503_MAX_RETRIES = 2  # 3 attempts total
GEMINI_503_RETRY_BACKOFF_SECONDS = (1, 2)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

_WRITING_CATEGORIES = SKILL_ERROR_CATEGORIES["writing"]
_WRITING_CATEGORY_KEYS = frozenset(key for key, _ in _WRITING_CATEGORIES)
_CATEGORY_LIST_FOR_PROMPT = "\n".join(f"- {key}: {label}" for key, label in _WRITING_CATEGORIES)

# Enforced by Gemini at decode time (responseMimeType + responseSchema below),
# not just requested in prompt text like the Ollama version was — the model
# structurally cannot emit a category outside this enum. The post-hoc filter
# in grade_writing_submission() stays anyway as defense in depth.
_WRITING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "rubric_score": {"type": "integer"},
        "feedback_summary": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": sorted(_WRITING_CATEGORY_KEYS)},
                    "example": {"type": "string"},
                },
                "required": ["category", "example"],
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rubric_score", "feedback_summary", "errors", "recommendations"],
}

# Draft copy, same provisional status as speaking_tutor.LEVEL_DIFFICULTY_GUIDANCE.
LEVEL_GRADING_GUIDANCE = {
    "A1": "The learner is A1 (beginner). Grade generously — focus feedback on only the most basic errors, and use very simple language in your feedback.",
    "A2": "The learner is A2 (elementary). Focus feedback on common everyday mistakes, keep it simple and encouraging.",
    "B1": "The learner is B1 (intermediate). Expect basic fluency; focus feedback on grammar consistency and clarity.",
    "B2": "The learner is B2 (upper-intermediate). Expect natural phrasing; focus feedback on nuance, word choice, and structure.",
    "C1": "The learner is C1 (advanced). Hold to a higher bar; focus feedback on style, precision, and subtlety.",
    "C2": "The learner is C2 (proficient). Grade close to native-level expectations; focus feedback on refinement and idiomatic naturalness.",
}

RESPONSE_SHAPE_INSTRUCTIONS = (
    # No longer asks for JSON formatting/shape here -- generationConfig's
    # responseMimeType + responseSchema enforce that structurally now. This
    # is field-level semantic guidance the schema can't express on its own.
    "rubric_score is 0-100 reflecting grammar correctness, task completion, and clarity for this learner's level.\n"
    "errors: only include a category if you see a real, clear instance in the learner's own writing — "
    "classify each into EXACTLY ONE of these categories (use the key exactly as written, do not invent new ones):\n"
    f"{_CATEGORY_LIST_FOR_PROMPT}\n"
    "recommendations: at most 2-3 short, higher-level observations (structure, word variety, tone) — "
    "distinct from the pointwise errors above, not a restatement of them.\n"
    "If the writing has no clear errors, output an empty errors list."
)


def _build_grading_prompt(
    *, prompt_text: str, min_words: int | None, max_words: int | None, cefr_level: str | None, error_context: str
) -> str:
    guidance = LEVEL_GRADING_GUIDANCE.get(cefr_level, LEVEL_GRADING_GUIDANCE["A1"])
    length_hint = ""
    if min_words:
        length_hint = f" Target length was {min_words}"
        if max_words:
            length_hint += f"-{max_words}"
        length_hint += " words."

    sections = [
        "You are grading a piece of writing from an English learner practicing for the TOEIC exam.",
        f'The writing prompt was: "{prompt_text}"{length_hint}',
        guidance,
    ]
    if error_context:
        sections.append(error_context)
    sections.append(RESPONSE_SHAPE_INSTRUCTIONS)
    return "\n\n".join(sections)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def grade_writing_submission(
    *,
    user,
    essay: str,
    prompt_text: str,
    min_words: int | None,
    max_words: int | None,
    cefr_level: str | None,
) -> dict | None:
    """Single Gemini call: rubric score + feedback + errors + recommendations.
    Returns None on any failure — caller must fall back to the placeholder."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None  # optional by design, same as Ollama being unreachable — no key, no call, straight to placeholder
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    error_context = format_error_context_for_prompt(get_top_error_patterns(user, "writing"))
    system_prompt = _build_grading_prompt(
        prompt_text=prompt_text,
        min_words=min_words,
        max_words=max_words,
        cefr_level=cefr_level,
        error_context=error_context,
    )

    try:
        for attempt in range(GEMINI_503_MAX_RETRIES + 1):
            response = httpx.post(
                f"{GEMINI_API_BASE_URL}/{model}:generateContent",
                headers={"x-goog-api-key": api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": essay}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        # 500 was enough for Ollama (no hidden reasoning tokens);
                        # Gemini 3.x "thinking" models spend part of the output
                        # budget on invisible reasoning before the visible JSON,
                        # and that thinking-token spend varies noticeably between
                        # calls even at the same essay/prompt -- 2048 still
                        # truncated (finishReason: MAX_TOKENS) on roughly half of
                        # live test calls. 4096 leaves enough headroom to make
                        # that rare rather than routine.
                        "maxOutputTokens": 4096,
                        "responseMimeType": "application/json",
                        "responseSchema": _WRITING_RESPONSE_SCHEMA,
                    },
                },
                timeout=GRADING_TIMEOUT_SECONDS,
            )
            if response.status_code != 503 or attempt == GEMINI_503_MAX_RETRIES:
                break
            time.sleep(GEMINI_503_RETRY_BACKOFF_SECONDS[attempt])
        if response.status_code != 200:
            return None  # covers 429/503-after-retries/etc same as any other failure -- straight to placeholder
        candidates = response.json().get("candidates") or []
        if not candidates:
            return None  # empty when Gemini's safety filters block the prompt or the output
        parts = candidates[0].get("content", {}).get("parts") or []
        content = parts[0].get("text", "") if parts else ""
        parsed = json.loads(_strip_code_fences(content))
    except (httpx.HTTPError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    score = parsed.get("rubric_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return None
    rubric_score = max(0, min(100, int(score)))

    feedback_summary = str(parsed.get("feedback_summary", "")).strip()
    if not feedback_summary:
        return None

    errors = []
    raw_errors = parsed.get("errors")
    if isinstance(raw_errors, list):
        for item in raw_errors:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            example = str(item.get("example", "")).strip()
            if category in _WRITING_CATEGORY_KEYS:
                errors.append({"category": category, "example": example})

    recommendations = []
    raw_recommendations = parsed.get("recommendations")
    if isinstance(raw_recommendations, list):
        recommendations = [str(r).strip() for r in raw_recommendations if str(r).strip()][:3]

    return {
        "rubric_score": rubric_score,
        "feedback_summary": feedback_summary,
        "errors": errors,
        "recommendations": recommendations,
    }


def record_writing_errors(user, errors: list[dict]) -> None:
    """Persist each detected error via the shared TutorErrorPattern model."""
    for item in errors:
        record_error_pattern(user, "writing", item["category"], item["example"])


def build_weak_points_summary(user) -> str:
    """Cross-session recurring-issue summary for display — direct reuse of
    the same query Speaking's tutor-context injection already runs, just
    rendered for the student instead of injected into another prompt."""
    patterns = get_top_error_patterns(user, "writing")
    if not patterns:
        return ""
    items = "; ".join(f"{p.get_category_display()} ({p.occurrence_count}x)" for p in patterns)
    return f"Your most common issue lately: {items}."
