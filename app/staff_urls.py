from django.urls import path

from . import staff_views

urlpatterns = [
    path("lesson-builder/", staff_views.lesson_builder_index, name="staff_lesson_builder"),
    path("lesson-builder/<slug:skill_slug>/", staff_views.lesson_list, name="staff_lesson_list"),
    path("lesson-builder/<slug:skill_slug>/new/", staff_views.lesson_create, name="staff_lesson_create"),
    path(
        "lesson-builder/<slug:skill_slug>/<int:lesson_id>/edit/",
        staff_views.lesson_edit,
        name="staff_lesson_edit",
    ),
    path(
        "lesson-builder/<slug:skill_slug>/<int:lesson_id>/delete/",
        staff_views.lesson_delete,
        name="staff_lesson_delete",
    ),
]
