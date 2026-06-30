"""
Gamification spec — single source of truth for XP, accuracy, and progression.

All skills (Speaking, Listening, Reading, Writing, Vocabulary) must use these
constants and helpers via stats_service. Do not invent per-skill XP scales elsewhere.
"""

from __future__ import annotations

from decimal import Decimal

# ---------------------------------------------------------------------------
# Daily goals & level caps
# ---------------------------------------------------------------------------
DAILY_LESSON_GOAL = 5
MAX_SKILL_LEVEL = 15
XP_PER_GLOBAL_LEVEL = 400

# ---------------------------------------------------------------------------
# XP awards
# ---------------------------------------------------------------------------
XP_PER_QUIZ_CORRECT = 10
XP_LESSON_COMPLETE = 25

XP_PER_SPEAKING_TURN = 15
XP_SPEAKING_SESSION_BONUS = 25
MIN_SPEAKING_TURNS_FOR_BONUS = 2

XP_WRITING_BASE = 25
XP_WRITING_SCORE_MULTIPLIER = Decimal("0.3")

# ---------------------------------------------------------------------------
# Vocabulary mastery (words_learned on UserProfile)
# ---------------------------------------------------------------------------
VOCABULARY_MASTERY_CORRECT_THRESHOLD = 3

# ---------------------------------------------------------------------------
# Accuracy helpers
# ---------------------------------------------------------------------------


def estimate_speaking_turn_accuracy(message: str) -> int:
    """Engagement proxy for Speaking until pronunciation scoring exists."""
    words = len(message.split())
    if words < 2:
        return 40
    return min(100, 50 + words * 5)


def compute_quiz_accuracy(correct: int, total: int) -> Decimal | None:
    """Standard accuracy for Listening / Reading / Vocabulary quizzes."""
    if total <= 0:
        return None
    return Decimal(correct * 100 / total).quantize(Decimal("0.01"))


def compute_speaking_session_xp(user_turn_count: int) -> int:
    xp = user_turn_count * XP_PER_SPEAKING_TURN
    if user_turn_count >= MIN_SPEAKING_TURNS_FOR_BONUS:
        xp += XP_SPEAKING_SESSION_BONUS
    return xp


def compute_quiz_lesson_xp(correct: int, total: int) -> int:
    """XP for a completed quiz lesson (correct answers + completion bonus)."""
    if total <= 0:
        return 0
    return (correct * XP_PER_QUIZ_CORRECT) + XP_LESSON_COMPLETE


def compute_writing_lesson_xp(rubric_score: int) -> int:
    """XP for a completed writing lesson (base + score bonus)."""
    score = max(0, min(100, rubric_score))
    bonus = int(Decimal(score) * XP_WRITING_SCORE_MULTIPLIER)
    return XP_WRITING_BASE + bonus


def compute_global_level(total_xp: int) -> int:
    """Sidebar / profile global level from total XP."""
    return max(1, total_xp // XP_PER_GLOBAL_LEVEL + 1)


def global_level_progress_percent(total_xp: int) -> int:
    """Progress toward the next global level (0–100)."""
    if total_xp <= 0:
        return 0
    xp_into_level = total_xp % XP_PER_GLOBAL_LEVEL
    return min(100, round(xp_into_level * 100 / XP_PER_GLOBAL_LEVEL))


def global_level_label(level: int) -> str:
    if level <= 3:
        return "Beginner"
    if level <= 7:
        return "Intermediate"
    if level <= 11:
        return "Advanced"
    return "Fluent"
