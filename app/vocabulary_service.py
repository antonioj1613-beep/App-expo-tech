"""
Vocabulary review — SM-2 spaced repetition over the staff-managed SkillLesson
catalog (skill=vocabulary). Deliberately separate from lesson_service.py:
every other staff-managed skill picks "the next lesson" by walking the
catalog in order and stopping at the first uncompleted one, but spaced
repetition breaks that assumption entirely — a word can be shown again long
after it was first "completed". Catalog-completion tracking (Levels page,
sidebar nav pills) is untouched and keeps working exactly as before via
UserSkillLessonCompletion; this module only drives the dedicated
/vocabulary/ review page and its submit endpoint.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .gamification import VOCABULARY_MASTERY_REPETITIONS, apply_sm2_review, compute_vocab_review_xp
from .models import SkillLesson, User, UserSkillLessonCompletion, UserVocabularyReviewState
from .stats_service import build_skill_context, record_practice_session

SKILL_SLUG = "vocabulary"
REVIEW_BATCH_SIZE = 10
VOCAB_REVIEW_DURATION_SECONDS = 20  # a flashcard flip, not a full quiz lesson


def _published_vocabulary_lessons():
    return SkillLesson.objects.filter(skill__slug=SKILL_SLUG, is_published=True).order_by("sort_order", "id")


def get_due_vocabulary_lessons(user: User, limit: int = REVIEW_BATCH_SIZE) -> list[SkillLesson]:
    """
    Due = never reviewed (no UserVocabularyReviewState row) or
    next_review_date <= today. Never-reviewed words are served first
    (introduce new content before repeating a backlog), then the most
    overdue reviewed words.
    """
    lessons = list(_published_vocabulary_lessons())
    if not lessons:
        return []

    lessons_by_id = {lesson.id: lesson for lesson in lessons}
    reviewed_ids = set(
        UserVocabularyReviewState.objects.filter(user=user, lesson_id__in=lessons_by_id).values_list(
            "lesson_id", flat=True
        )
    )
    new_lessons = [lesson for lesson in lessons if lesson.id not in reviewed_ids]

    today = timezone.localdate()
    due_states = (
        UserVocabularyReviewState.objects.filter(
            user=user, lesson_id__in=lessons_by_id, next_review_date__lte=today
        )
        .order_by("next_review_date")[:limit]
        .values_list("lesson_id", flat=True)
    )
    due_lessons = [lessons_by_id[lid] for lid in due_states]

    if len(due_lessons) < limit:
        due_lessons += new_lessons[: limit - len(due_lessons)]
    return due_lessons


def get_next_due_vocabulary_lesson(user: User) -> SkillLesson | None:
    lessons = get_due_vocabulary_lessons(user, limit=1)
    return lessons[0] if lessons else None


def vocabulary_page_state(user: User) -> dict:
    total = _published_vocabulary_lessons().count()
    has_lessons = total > 0
    next_lesson = get_next_due_vocabulary_lesson(user) if has_lessons else None
    return {
        "has_lessons": has_lessons,
        "coming_soon": not has_lessons,
        "all_caught_up": has_lessons and next_lesson is None,
        "next_lesson": next_lesson,
        "total_lessons": total,
    }


def submit_vocabulary_review(user: User, lesson_id: int, correct: bool) -> dict:
    try:
        lesson = SkillLesson.objects.get(pk=lesson_id, skill__slug=SKILL_SLUG)
    except SkillLesson.DoesNotExist:
        return {"error": "Word not found.", "status": 404}

    state, is_first_review = UserVocabularyReviewState.objects.get_or_create(user=user, lesson=lesson)

    new_ease, new_interval, new_reps = apply_sm2_review(
        correct=correct,
        ease_factor=state.ease_factor,
        interval_days=state.interval_days,
        repetition_count=state.repetition_count,
    )
    state.ease_factor = new_ease
    state.interval_days = new_interval
    state.repetition_count = new_reps
    state.next_review_date = timezone.localdate() + timedelta(days=new_interval)
    state.last_reviewed_at = timezone.now()
    state.save(
        update_fields=[
            "ease_factor",
            "interval_days",
            "repetition_count",
            "next_review_date",
            "last_reviewed_at",
            "updated_at",
        ]
    )

    xp_earned = compute_vocab_review_xp(correct=correct, is_first_review=is_first_review)

    if is_first_review:
        UserSkillLessonCompletion.objects.create(
            user=user, lesson=lesson, was_correct=correct, xp_earned=xp_earned
        )

    record_practice_session(
        user,
        skill_slug=SKILL_SLUG,
        xp_earned=xp_earned,
        accuracy_score=Decimal(100) if correct else Decimal(0),
        duration_seconds=VOCAB_REVIEW_DURATION_SECONDS,
        lessons_completed=1 if is_first_review else 0,
        lesson_level=lesson.level,
    )

    next_lesson = get_next_due_vocabulary_lesson(user)
    skill = build_skill_context(user, SKILL_SLUG)

    return {
        "ok": True,
        "correct": correct,
        "is_first_review": is_first_review,
        "xp_earned": xp_earned,
        "next_review_date": state.next_review_date.isoformat(),
        "interval_days": new_interval,
        "mastered": new_reps >= VOCABULARY_MASTERY_REPETITIONS,
        "has_next": next_lesson is not None,
        "skill": skill,
    }
