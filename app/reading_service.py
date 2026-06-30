"""Reading lesson selection and completion — delegates to lesson_service."""

from __future__ import annotations

from .lesson_service import build_lesson_context, get_next_lesson_for_user, submit_quiz_answer
from .models import User

READING_LESSON_DURATION_SECONDS = 180


def get_reading_lesson_for_user(user: User):
    return get_next_lesson_for_user(user, "reading")


def build_reading_lesson_context(lesson, user: User) -> dict:
    return build_lesson_context(lesson, user, "reading")


def submit_reading_answer(user: User, lesson_id: int, selected_index: int) -> dict:
    return submit_quiz_answer(user, "reading", lesson_id, selected_index)
