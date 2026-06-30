"""Build Levels page and catalog state for staff-managed skills."""

from __future__ import annotations

from collections import defaultdict

from .lesson_service import STAFF_MANAGED_SKILLS, get_next_lesson_for_user, published_lessons
from .models import Skill, User, UserSkillLessonCompletion
from .stats_service import SKILL_UI_META, ensure_user_skill_progress, get_skill_progress_row

SKILL_LEVEL_META = {
    "listening": ("headphones", "Train your ear with real-world audio"),
    "reading": ("book-open", "Build comprehension from texts at your level"),
    "writing": ("pen-line", "Practice writing with instant AI feedback"),
    "vocabulary": ("graduation-cap", "Grow your word bank with smart repetition"),
}

COMING_SOON_MESSAGE = "More levels are coming"


def _completed_lesson_ids(user: User, skill_slug: str) -> set[int]:
    return set(
        UserSkillLessonCompletion.objects.filter(user=user, lesson__skill__slug=skill_slug).values_list(
            "lesson_id", flat=True
        )
    )


def build_skill_levels_panel(user: User, skill_slug: str) -> dict:
    """Per-skill data for the Levels page grid."""
    ensure_user_skill_progress(user)
    icon, tagline = SKILL_LEVEL_META.get(skill_slug, ("layers", ""))
    meta = SKILL_UI_META.get(skill_slug, {})
    progress = get_skill_progress_row(user, skill_slug)
    skill_obj = Skill.objects.filter(slug=skill_slug).first()

    lessons = list(published_lessons(skill_slug))
    has_lessons = len(lessons) > 0
    completed_ids = _completed_lesson_ids(user, skill_slug)
    next_lesson = get_next_lesson_for_user(user, skill_slug) if has_lessons else None
    catalog_complete = has_lessons and next_lesson is None

    ordered_ids = [lesson.id for lesson in lessons]
    next_index = ordered_ids.index(next_lesson.id) if next_lesson else len(ordered_ids)

    by_level: dict[int, list] = defaultdict(list)
    for lesson in lessons:
        by_level[lesson.level].append(lesson)

    level_cards = []
    for level_num in range(1, 16):
        level_lessons = by_level.get(level_num, [])
        if not level_lessons:
            continue

        indices = [ordered_ids.index(lesson.id) for lesson in level_lessons]
        first_index = min(indices)
        last_index = max(indices)
        all_complete = all(lesson.id in completed_ids for lesson in level_lessons)
        is_current = next_lesson is not None and next_lesson.id in {lesson.id for lesson in level_lessons}
        unlocked = last_index <= next_index

        level_cards.append(
            {
                "n": level_num,
                "title": level_lessons[0].title,
                "lesson_count": len(level_lessons),
                "completed": all_complete,
                "unlocked": unlocked,
                "is_current": is_current,
            }
        )

    total = len(lessons)
    completed_count = len(completed_ids)
    progress_percent = min(100, round(completed_count * 100 / total)) if total else 0

    return {
        "id": skill_slug,
        "name": skill_obj.name if skill_obj else skill_slug.title(),
        "icon": icon,
        "tagline": tagline,
        "url": meta.get("url", skill_slug),
        "has_lessons": has_lessons,
        "catalog_complete": catalog_complete,
        "coming_soon": not has_lessons or catalog_complete,
        "coming_soon_message": COMING_SOON_MESSAGE,
        "level_cards": level_cards,
        "total_lessons": total,
        "completed_count": completed_count,
        "progress_percent": progress_percent,
        "lessons_label": f"{completed_count} / {total}" if has_lessons else "0 / 0",
        "continue_url": meta.get("url", skill_slug),
        "current_level": next_lesson.level if next_lesson else (level_cards[-1]["n"] if catalog_complete and level_cards else None),
    }


def build_levels_page_skills(user: User) -> list[dict]:
    panels = [build_skill_levels_panel(user, slug) for slug in STAFF_MANAGED_SKILLS]
    speaking = Skill.objects.filter(slug="speaking").first()
    if speaking:
        meta = SKILL_UI_META.get("speaking", {})
        panels.append(
            {
                "id": "speaking",
                "name": speaking.name,
                "icon": meta.get("icon", "mic"),
                "tagline": "Voice conversation practice with AI tutors Miles & Maya",
                "url": "speaking",
                "is_speaking": True,
                "lessons": "Voice chat",
            }
        )
    return panels


def build_nav_skill_states(user: User | None) -> dict[str, dict]:
    """Shortcut metadata for sidebar skill links below Levels."""
    states: dict[str, dict] = {}
    for slug in STAFF_MANAGED_SKILLS:
        lessons = list(published_lessons(slug))
        has_lessons = len(lessons) > 0
        next_lesson = get_next_lesson_for_user(user, slug) if user and has_lessons else None
        catalog_complete = has_lessons and next_lesson is None
        states[slug] = {
            "has_lessons": has_lessons,
            "catalog_complete": catalog_complete,
            "current_level": next_lesson.level if next_lesson else None,
            "empty": not has_lessons,
            "coming_soon": not has_lessons or catalog_complete,
        }
    return states
