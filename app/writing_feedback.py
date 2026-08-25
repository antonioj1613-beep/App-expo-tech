"""
Writing submit-time AI grading — writing feature.

One combined Ollama call per submission, returning a holistic rubric
score, prose feedback, detected error patterns, and higher-level
recommendations in a single JSON response. Combined into one call rather
than split like Speaking's live-reply/post-session-extraction split,
because a Writing submission happens once per lesson attempt — there's no
"keep the hot path fast" pressure the way Speaking's live chat turns have,
so splitting would only multiply the worst-case wait for no benefit.

On any failure (Ollama down, timeout, bad JSON, missing required fields)
this returns None — the caller (writing_views.writing_submit) falls back
to the pre-existing word-count placeholder, exactly like Speaking falls
back to _fallback_reply() when Ollama is unavailable.

Kept separate from tutor_memory.py (which stays skill-agnostic — record
storage + injection query only) and doesn't extend
tutor_memory.run_error_extraction(), whose transcript-shaped input and
Speaking-specific prompt don't fit a single essay submission.
"""

from __future__ import annotations

import json
import os

import httpx

from .gamification import SKILL_ERROR_CATEGORIES
from .tutor_memory import format_error_context_for_prompt, get_top_error_patterns, record_error_pattern

GRADING_TIMEOUT_SECONDS = 20.0  # a submit-time call the student is waiting on,
# same graceful-degradation shape as Speaking's post-session extraction,
# just a shorter budget since nothing else in the response depends on it.

_WRITING_CATEGORIES = SKILL_ERROR_CATEGORIES["writing"]
_WRITING_CATEGORY_KEYS = frozenset(key for key, _ in _WRITING_CATEGORIES)
_CATEGORY_LIST_FOR_PROMPT = "\n".join(f"- {key}: {label}" for key, label in _WRITING_CATEGORIES)

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
    "Output ONLY valid JSON, no markdown fences, no other text, in exactly this shape:\n"
    '{"rubric_score": 78, "feedback_summary": "one short encouraging paragraph, 2-3 sentences", '
    '"errors": [{"category": "articles", "example": "short quoted snippet under 15 words"}], '
    '"recommendations": ["one short actionable sentence", "..."]}\n'
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
    """Single Ollama call: rubric score + feedback + errors + recommendations.
    Returns None on any failure — caller must fall back to the placeholder."""
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")

    error_context = format_error_context_for_prompt(get_top_error_patterns(user, "writing"))
    system_prompt = _build_grading_prompt(
        prompt_text=prompt_text,
        min_words=min_words,
        max_words=max_words,
        cefr_level=cefr_level,
        error_context=error_context,
    )

    try:
        response = httpx.post(
            f"{url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": essay},
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 500},
            },
            timeout=GRADING_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            return None
        content = response.json().get("message", {}).get("content", "")
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
