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

# First-time review of a new word earns lesson-completion-style XP (matches
# other skills' one-time bonus). Repeat reviews earn a small flat amount —
# spaced repetition means the same word gets reviewed indefinitely, so full
# lesson XP every time would let a student farm XP by re-reviewing one word
# forever instead of progressing through the catalog.
XP_VOCAB_FIRST_REVIEW = XP_LESSON_COMPLETE
XP_VOCAB_REPEAT_CORRECT = 5
XP_VOCAB_REPEAT_INCORRECT = 2

# words_learned on UserProfile / vocabulary "mastered" stat: a word is
# considered mastered after this many consecutive successful SM-2
# repetitions (mirrors the old correct-streak threshold's value, applied to
# the new repetition_count instead of a simple correct-answer counter).
VOCABULARY_MASTERY_REPETITIONS = 3

# ---------------------------------------------------------------------------
# Spaced repetition — SM-2, binary-graded variant.
#
# Classic SM-2 grades recall quality on a 0-5 scale. This app has no
# precedent anywhere for a multi-point self-assessment control — every quiz
# skill (Reading/Listening) is single-correct-answer, binary right/wrong.
# Introducing a 5-point "how well did you know this" widget would be a new
# UI pattern nothing else in the app uses. Instead: binary correct/incorrect
# (the student's own "Got it" / "Still learning" choice) is mapped onto the
# two ends of SM-2's quality scale — full credit (behaves like classic q=5)
# on success, a fixed penalty (between classic q=0 and q=2) on failure. This
# is a documented, common simplification of SM-2 for binary-graded review
# apps; it loses the "recalled but with difficulty" middle grade, trading
# some scheduling nuance for an interface that matches the rest of the app.
# ---------------------------------------------------------------------------
SM2_INITIAL_EASE_FACTOR = Decimal("2.5")
SM2_MIN_EASE_FACTOR = Decimal("1.3")
SM2_EASE_BONUS_ON_CORRECT = Decimal("0.1")
SM2_EASE_PENALTY_ON_INCORRECT = Decimal("0.2")
SM2_SECOND_INTERVAL_DAYS = 6


def apply_sm2_review(
    *,
    correct: bool,
    ease_factor: Decimal,
    interval_days: int,
    repetition_count: int,
) -> tuple[Decimal, int, int]:
    """
    Advance one SM-2 review state by a single binary-graded review.

    Returns (new_ease_factor, new_interval_days, new_repetition_count).
    Caller is responsible for turning interval_days into an actual
    next_review_date (this function is deliberately date-free and pure).
    """
    if not correct:
        return (
            max(SM2_MIN_EASE_FACTOR, ease_factor - SM2_EASE_PENALTY_ON_INCORRECT),
            1,
            0,
        )

    new_repetition_count = repetition_count + 1
    if new_repetition_count == 1:
        new_interval = 1
    elif new_repetition_count == 2:
        new_interval = SM2_SECOND_INTERVAL_DAYS
    else:
        new_interval = max(1, round(interval_days * float(ease_factor)))

    new_ease_factor = max(SM2_MIN_EASE_FACTOR, ease_factor + SM2_EASE_BONUS_ON_CORRECT)
    return new_ease_factor, new_interval, new_repetition_count


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


def compute_vocab_review_xp(*, correct: bool, is_first_review: bool) -> int:
    """XP for one vocabulary review — see the XP_VOCAB_* constants for why
    first-time and repeat reviews are weighted so differently."""
    if is_first_review:
        return XP_VOCAB_FIRST_REVIEW
    return XP_VOCAB_REPEAT_CORRECT if correct else XP_VOCAB_REPEAT_INCORRECT


# ---------------------------------------------------------------------------
# CEFR sub-leveling (per skill) — Phase 1.
#
# Replaces the old XP-derived global level as the authoritative "how good is
# this student at this skill" signal. XP/streak remain their own independent
# stats (see UserProfile) — they no longer imply a level.
#
# Design (see Phase 1 design doc, provisional pending real usage data):
# - Each graded interaction (a PracticeSession row) optionally carries the
#   lesson_level (1-15) it was attempted at. Speaking has no discrete lesson
#   catalog, so its interactions carry lesson_level=None; for Speaking we
#   treat the *band currently being tested* as the student's own current
#   cefr_level, since the tutor already adapts its difficulty to that level.
# - CEFR_ROLLING_WINDOW most recent graded interactions per skill are
#   averaged for accuracy. Below CEFR_MIN_INTERACTIONS total ever recorded,
#   the skill is "not yet assessed" (None) rather than defaulting to A1.
# - Promotion needs sustained accuracy at the currently-tested band;
#   demotion needs a sustained *drop*. The asymmetry (75% up / 50% down) is
#   deliberate hysteresis to stop the level flapping on a single session.
# ---------------------------------------------------------------------------
CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

# Lesson difficulty (SkillLesson.level, 1-15) -> CEFR band. Provisional
# partition pending real rolling-window usage data.
LESSON_LEVEL_TO_CEFR_BAND = {
    1: "A1", 2: "A1",
    3: "A2", 4: "A2",
    5: "B1", 6: "B1", 7: "B1",
    8: "B2", 9: "B2",
    10: "C1", 11: "C1", 12: "C1",
    13: "C2", 14: "C2", 15: "C2",
}

CEFR_ROLLING_WINDOW = 10
CEFR_MIN_INTERACTIONS = 3
CEFR_PROMOTION_THRESHOLD = 75
CEFR_DEMOTION_THRESHOLD = 50


def lesson_level_to_cefr_band(lesson_level: int) -> str:
    return LESSON_LEVEL_TO_CEFR_BAND.get(max(1, min(15, lesson_level)), "A1")


def recompute_cefr_level(
    rolling_pairs: list[tuple[float, int | None]],
    *,
    total_interaction_count: int,
    current_level: str | None,
) -> str | None:
    """
    Compute a skill's new CEFR level from its rolling window of recent
    graded interactions.

    rolling_pairs: up to CEFR_ROLLING_WINDOW (accuracy_score, lesson_level)
        tuples, most-recent-first. lesson_level is None for Speaking.
    total_interaction_count: total graded interactions ever recorded for
        this (user, skill) — gates the "not yet assessed" fallback
        independent of window size.
    current_level: the skill's existing CEFR level, or None if unassessed.
    """
    if total_interaction_count < CEFR_MIN_INTERACTIONS or not rolling_pairs:
        return None

    _, latest_lesson_level = rolling_pairs[0]
    rolling_accuracy = sum(a for a, _ in rolling_pairs) / len(rolling_pairs)

    if latest_lesson_level is not None:
        # Lesson-based skills: an external difficulty ladder exists
        # (SkillLesson.level). The band under test is whatever the most
        # recently attempted lesson was — for a sequentially-walked
        # catalog that's naturally the frontier of the student's progress.
        candidate_band = lesson_level_to_cefr_band(latest_lesson_level)

        if current_level is None:
            # First-ever assessment: no prior value to hold or demote from.
            return candidate_band
        if rolling_accuracy >= CEFR_PROMOTION_THRESHOLD:
            return candidate_band
        if rolling_accuracy < CEFR_DEMOTION_THRESHOLD:
            idx = CEFR_LEVELS.index(current_level) if current_level in CEFR_LEVELS else 0
            return CEFR_LEVELS[max(0, idx - 1)]
        return current_level  # ambiguous middle zone: hold steady, don't flap

    # Speaking: no discrete lesson ladder. The tutor already adapts its
    # difficulty to the student's current cefr_level (see speaking_tutor.py),
    # so unlike lesson-based skills there's no separate "next band" signal
    # to read — sustained strong accuracy at the current adaptive difficulty
    # IS the promotion signal, so it must move the level up one band itself,
    # not just re-confirm the same band (which would make promotion
    # impossible once first assessed).
    if current_level is None:
        return "A1"  # first assessment: the tutor's own default floor
    idx = CEFR_LEVELS.index(current_level) if current_level in CEFR_LEVELS else 0
    if rolling_accuracy >= CEFR_PROMOTION_THRESHOLD:
        return CEFR_LEVELS[min(len(CEFR_LEVELS) - 1, idx + 1)]
    if rolling_accuracy < CEFR_DEMOTION_THRESHOLD:
        return CEFR_LEVELS[max(0, idx - 1)]
    return current_level


def derive_overall_cefr_level(skill_levels: list[str | None]) -> str | None:
    """Median of assessed per-skill CEFR levels (ordinal scale — no mean)."""
    assessed = sorted(
        (CEFR_LEVELS.index(lvl) for lvl in skill_levels if lvl in CEFR_LEVELS)
    )
    if not assessed:
        return None
    mid = len(assessed) // 2
    if len(assessed) % 2 == 1:
        return CEFR_LEVELS[assessed[mid]]
    # Even count: average the two middle ordinal indices, round down
    # (conservative — don't credit a level the student hasn't clearly hit).
    return CEFR_LEVELS[(assessed[mid - 1] + assessed[mid]) // 2]


# ---------------------------------------------------------------------------
# Tutor error-pattern taxonomy — Phase 3.
#
# Lives here (not in tutor_memory.py, where the rest of Phase 3's logic
# lives) for the same reason CEFR_LEVELS lives here rather than in
# models.py: models.py needs these as field choices, and tutor_memory.py
# needs both this taxonomy AND the models it describes, so the taxonomy has
# to sit somewhere neither of those two modules depends on the other for.
# gamification.py imports nothing from models.py, so it's the safe common
# ground — same role it already plays for CEFR_LEVELS.
#
# Bounded and small on purpose: a bigger, more granular list gives finer
# tracking but a small local model (Phi-3-mini) classifies less reliably as
# the option list grows. Provisional pending real classification data —
# same status as the CEFR bands above.
# ---------------------------------------------------------------------------
ERROR_CATEGORIES = [
    ("verb_tense_past_perfect", "Past perfect vs. simple past"),
    ("verb_tense_present_perfect", "Present perfect vs. simple past"),
    ("subject_verb_agreement", "Subject-verb agreement"),
    ("articles", "Article usage (a / an / the)"),
    ("prepositions", "Preposition usage"),
    ("word_order", "Word order"),
    ("modal_verbs", "Modal verbs (can / could / should / would...)"),
    ("countable_uncountable_nouns", "Countable vs. uncountable nouns"),
    ("th_sound", '"Th" sound pronunciation'),
    ("r_l_distinction", "R/L sound distinction"),
    ("word_stress_intonation", "Word stress and intonation"),
    ("false_friends_word_choice", "False friends / word choice"),
    ("spelling", "Spelling"),
    ("run_on_sentences", "Run-on sentences and comma splices"),
    ("punctuation", "Punctuation usage"),
]
ERROR_CATEGORY_KEYS = frozenset(key for key, _ in ERROR_CATEGORIES)

# Per-skill subsets -- each skill's extraction prompt should only offer its
# own relevant categories, not the full merged list above (Speaking's
# prompt shouldn't be able to tag "punctuation", Writing's shouldn't see
# "th_sound"). Speaking's subset is exactly the original 12, unchanged from
# before the 3 writing-only additions above -- zero behavior change to the
# already-shipped Speaking error memory.
_SPEAKING_ONLY_CATEGORIES = frozenset({"th_sound", "r_l_distinction", "word_stress_intonation"})
_WRITING_ONLY_CATEGORIES = frozenset({"spelling", "run_on_sentences", "punctuation"})
SKILL_ERROR_CATEGORIES = {
    "speaking": [pair for pair in ERROR_CATEGORIES if pair[0] not in _WRITING_ONLY_CATEGORIES],
    "writing": [pair for pair in ERROR_CATEGORIES if pair[0] not in _SPEAKING_ONLY_CATEGORIES],
}


# ---------------------------------------------------------------------------
# Streak freeze — Phase 4
#
# Earn: 1 freeze per streak_days crossing a multiple of this interval, capped
# at STREAK_FREEZE_MAX_STORED. Safe as a stateless modulo check because
# streak_days only ever changes by +1 or hard-resets to 1 (see
# stats_service._update_streak) — it can never skip past a multiple of the
# interval, so this can't double-award or miss an award.
#
# Both numbers are provisional, same status as the CEFR bands and error
# taxonomy above — tune with real usage data, not launch guesses.
# ---------------------------------------------------------------------------
STREAK_FREEZE_EARN_INTERVAL_DAYS = 7
STREAK_FREEZE_MAX_STORED = 2
