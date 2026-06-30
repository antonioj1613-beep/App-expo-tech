"""Shared lesson selection and quiz completion for staff-managed skills."""

from __future__ import annotations

from .gamification import compute_quiz_accuracy, compute_quiz_lesson_xp
from .models import STAFF_SKILL_SLUGS, SkillLesson, User, UserSkillLessonCompletion
from .stats_service import build_skill_context, ensure_user_skill_progress, get_skill_progress_row, record_practice_session

LESSON_DURATION_SECONDS = 180
STAFF_MANAGED_SKILLS = STAFF_SKILL_SLUGS
QUIZ_SKILL_SLUGS = frozenset({"listening", "reading"})
COMING_SOON_MESSAGE = "More levels are coming"


def published_lessons(skill_slug: str):
    return SkillLesson.objects.filter(skill__slug=skill_slug, is_published=True).order_by(
        "sort_order", "id"
    )


def has_published_lessons(skill_slug: str) -> bool:
    return published_lessons(skill_slug).exists()


def published_lesson_count(skill_slug: str) -> int:
    return published_lessons(skill_slug).count()


def is_catalog_complete(user: User, skill_slug: str) -> bool:
    if not has_published_lessons(skill_slug):
        return False
    return get_next_lesson_for_user(user, skill_slug) is None


def get_skill_page_state(user: User, skill_slug: str) -> dict:
    """Shared empty / complete / active state for skill lesson pages."""
    total = published_lesson_count(skill_slug)
    has_lessons = total > 0
    next_lesson = get_next_lesson_for_user(user, skill_slug) if has_lessons else None
    catalog_complete = has_lessons and next_lesson is None
    return {
        "has_lessons": has_lessons,
        "catalog_complete": catalog_complete,
        "coming_soon": not has_lessons or catalog_complete,
        "coming_soon_message": COMING_SOON_MESSAGE,
        "next_lesson": next_lesson,
        "total_lessons": total,
    }


def get_next_lesson_for_user(user: User, skill_slug: str) -> SkillLesson | None:
    """Return the next unpublished lesson in catalog order, or None if exhausted."""
    ensure_user_skill_progress(user)
    progress = get_skill_progress_row(user, skill_slug)
    completed_count = progress.lessons_completed if progress else 0
    return published_lessons(skill_slug)[completed_count : completed_count + 1].first()


def build_lesson_context(lesson: SkillLesson, user: User, skill_slug: str) -> dict:
    skill = build_skill_context(user, skill_slug)
    progress = get_skill_progress_row(user, skill_slug)
    completed = progress.lessons_completed if progress else 0
    total_seeded = published_lessons(skill_slug).count()
    lesson_number = completed + 1
    already_done = UserSkillLessonCompletion.objects.filter(user=user, lesson=lesson).exists()

    ctx = {
        "lesson_id": lesson.id,
        "lesson_title": lesson.title,
        "lesson_number": lesson_number,
        "lesson_total": total_seeded,
        "question_label": f"Lesson {lesson_number} of {total_seeded}",
        "already_completed": already_done,
        "skill": skill,
        "level": lesson.level,
    }

    if skill_slug in QUIZ_SKILL_SLUGS:
        ctx.update(
            {
                "passage": lesson.passage,
                "question_prompt": lesson.question_prompt,
                "options": lesson.options,
            }
        )
    elif skill_slug == "writing":
        ctx.update(
            {
                "writing_prompt": lesson.writing_prompt,
                "min_words": lesson.min_words,
                "max_words": lesson.max_words,
            }
        )
    elif skill_slug == "vocabulary":
        ctx.update(
            {
                "vocab_word": lesson.vocab_word,
                "vocab_ipa": lesson.vocab_ipa,
                "vocab_meaning": lesson.vocab_meaning,
                "vocab_example": lesson.vocab_example,
                "vocab_cefr": lesson.vocab_cefr,
            }
        )

    return ctx


def submit_quiz_answer(user: User, skill_slug: str, lesson_id: int, selected_index: int) -> dict:
    if skill_slug not in QUIZ_SKILL_SLUGS:
        return {"error": "This skill does not support quiz submission yet.", "status": 400}

    try:
        lesson = SkillLesson.objects.select_related("skill").get(pk=lesson_id, skill__slug=skill_slug)
    except SkillLesson.DoesNotExist:
        return {"error": "Lesson not found.", "status": 404}

    expected = get_next_lesson_for_user(user, skill_slug)
    if not expected or expected.id != lesson.id:
        return {"error": "This is not your current lesson.", "status": 400}

    if not isinstance(lesson.options, list) or not lesson.options:
        return {"error": "Lesson has no answer options.", "status": 500}

    if selected_index < 0 or selected_index >= len(lesson.options):
        return {"error": "Invalid answer selection.", "status": 400}

    was_correct = selected_index == lesson.correct_index
    already = UserSkillLessonCompletion.objects.filter(user=user, lesson=lesson).exists()

    xp_earned = 0
    accuracy = compute_quiz_accuracy(1 if was_correct else 0, 1)

    if not already:
        xp_earned = compute_quiz_lesson_xp(1 if was_correct else 0, 1)
        record_practice_session(
            user,
            skill_slug=skill_slug,
            xp_earned=xp_earned,
            accuracy_score=accuracy,
            duration_seconds=LESSON_DURATION_SECONDS,
            lessons_completed=1,
        )
        UserSkillLessonCompletion.objects.create(
            user=user,
            lesson=lesson,
            was_correct=was_correct,
            xp_earned=xp_earned,
        )

    next_lesson = get_next_lesson_for_user(user, skill_slug)
    skill = build_skill_context(user, skill_slug)

    return {
        "ok": True,
        "was_correct": was_correct,
        "correct_index": lesson.correct_index,
        "xp_earned": xp_earned,
        "accuracy": accuracy,
        "already_completed": already,
        "has_next_lesson": next_lesson is not None,
        "skill": skill,
    }
