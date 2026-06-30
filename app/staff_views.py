"""Superuser-only lesson builder for Listening, Reading, Writing, and Vocabulary."""

from __future__ import annotations

from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import SkillLessonStaffForm
from .models import STAFF_SKILL_SLUGS, Skill, SkillLesson

SKILL_META = {
    "listening": ("headphones", "Audio comprehension quizzes"),
    "reading": ("book-open", "Passage + comprehension questions"),
    "writing": ("pen-line", "Writing prompts with word targets"),
    "vocabulary": ("graduation-cap", "Word definitions and examples"),
}


def _superuser_check(user):
    return user.is_active and user.is_superuser


def superuser_required(view_func):
    return user_passes_test(_superuser_check, login_url="/admin/login/")(view_func)


def _get_staff_skill(slug: str) -> Skill:
    if slug not in STAFF_SKILL_SLUGS:
        raise Http404("Skill not available in lesson builder.")
    return get_object_or_404(Skill, slug=slug)


@superuser_required
def lesson_builder_index(request):
    skills = []
    for slug in STAFF_SKILL_SLUGS:
        skill = Skill.objects.filter(slug=slug).first()
        if not skill:
            continue
        icon, blurb = SKILL_META.get(slug, ("layers", ""))
        count = SkillLesson.objects.filter(skill=skill).count()
        published = SkillLesson.objects.filter(skill=skill, is_published=True).count()
        skills.append(
            {
                "skill": skill,
                "slug": slug,
                "icon": icon,
                "blurb": blurb,
                "count": count,
                "published": published,
            }
        )
    return render(request, "staff/lesson_builder_index.html", {"skills": skills})


@superuser_required
def lesson_list(request, skill_slug: str):
    skill = _get_staff_skill(skill_slug)
    lessons = SkillLesson.objects.filter(skill=skill).order_by("level", "sort_order", "id")
    by_level: dict[int, list] = defaultdict(list)
    for lesson in lessons:
        by_level[lesson.level].append(lesson)

    level_rows = []
    for level in range(1, 16):
        level_rows.append({"level": level, "lessons": by_level.get(level, [])})

    icon, blurb = SKILL_META.get(skill_slug, ("layers", ""))
    return render(
        request,
        "staff/lesson_list.html",
        {
            "skill": skill,
            "skill_slug": skill_slug,
            "icon": icon,
            "blurb": blurb,
            "level_rows": level_rows,
            "total_lessons": lessons.count(),
        },
    )


@superuser_required
def lesson_create(request, skill_slug: str):
    skill = _get_staff_skill(skill_slug)
    initial_level = request.GET.get("level")
    try:
        level_val = int(initial_level) if initial_level else 1
        if level_val < 1 or level_val > 15:
            level_val = 1
    except (TypeError, ValueError):
        level_val = 1

    if request.method == "POST":
        form = SkillLessonStaffForm(request.POST, skill_slug=skill_slug)
        if form.is_valid():
            lesson = form.save()
            messages.success(request, f'Created "{lesson.title}" for {skill.name} level {lesson.level}.')
            return redirect("staff_lesson_list", skill_slug=skill_slug)
    else:
        form = SkillLessonStaffForm(skill_slug=skill_slug, initial={"level": level_val})

    return render(
        request,
        "staff/lesson_form.html",
        {
            "form": form,
            "skill": skill,
            "skill_slug": skill_slug,
            "is_edit": False,
            "cancel_url": reverse("staff_lesson_list", kwargs={"skill_slug": skill_slug}),
        },
    )


@superuser_required
def lesson_edit(request, skill_slug: str, lesson_id: int):
    skill = _get_staff_skill(skill_slug)
    lesson = get_object_or_404(SkillLesson, pk=lesson_id, skill=skill)

    if request.method == "POST":
        form = SkillLessonStaffForm(request.POST, instance=lesson, skill_slug=skill_slug)
        if form.is_valid():
            form.save()
            messages.success(request, f'Updated "{lesson.title}".')
            return redirect("staff_lesson_list", skill_slug=skill_slug)
    else:
        form = SkillLessonStaffForm(instance=lesson, skill_slug=skill_slug)

    return render(
        request,
        "staff/lesson_form.html",
        {
            "form": form,
            "skill": skill,
            "skill_slug": skill_slug,
            "lesson": lesson,
            "is_edit": True,
            "cancel_url": reverse("staff_lesson_list", kwargs={"skill_slug": skill_slug}),
        },
    )


@superuser_required
@require_POST
def lesson_delete(request, skill_slug: str, lesson_id: int):
    skill = _get_staff_skill(skill_slug)
    lesson = get_object_or_404(SkillLesson, pk=lesson_id, skill=skill)
    title = lesson.title
    lesson.delete()
    messages.success(request, f'Deleted "{title}".')
    return redirect("staff_lesson_list", skill_slug=skill_slug)
