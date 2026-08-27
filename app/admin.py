from django.contrib import admin

from .models import (
    PracticeSession,
    Skill,
    SkillLesson,
    SpeakingSession,
    TutorErrorPattern,
    User,
    UserProfile,
    UserSkillLessonCompletion,
    UserSkillProgress,
    UserVocabularyReviewState,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "created_at")
    search_fields = ("username", "email")
    # password is a bcrypt hash, not a plaintext field — read-only so an admin
    # can't accidentally type a new value here and store it unhashed.
    readonly_fields = ("created_at", "password")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "streak_days",
        "streak_freezes",
        "total_xp",
        "avg_accuracy",
        "study_hours",
        "words_learned",
        "last_active_date",
        "last_freeze_consumed_at",
        "updated_at",
    )
    search_fields = ("user__username", "user__email")
    list_filter = ("native_language",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "total_lessons")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserSkillProgress)
class UserSkillProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "cefr_level", "status", "lessons_completed", "last_updated")
    list_filter = ("status", "skill", "cefr_level")
    search_fields = ("user__username",)
    readonly_fields = ("last_updated",)


@admin.register(SpeakingSession)
class SpeakingSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "tutor", "xp_earned", "accuracy_score", "duration_seconds", "created_at")
    list_filter = ("tutor",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


@admin.register(TutorErrorPattern)
class TutorErrorPatternAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "skill",
        "category",
        "occurrence_count",
        "last_detected_at",
        "resolved_at",
    )
    list_filter = ("category", "skill", ("resolved_at", admin.EmptyFieldListFilter))
    search_fields = ("user__username", "example_note")
    readonly_fields = ("first_detected_at", "last_detected_at")


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "xp_earned", "accuracy_score", "duration_seconds", "created_at")
    list_filter = ("skill",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


@admin.register(UserVocabularyReviewState)
class UserVocabularyReviewStateAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "lesson",
        "ease_factor",
        "interval_days",
        "repetition_count",
        "next_review_date",
        "last_reviewed_at",
    )
    list_filter = ("repetition_count",)
    search_fields = ("user__username", "lesson__vocab_word")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SkillLesson)
class SkillLessonAdmin(admin.ModelAdmin):
    list_display = ("title", "skill", "level", "sort_order", "is_published", "updated_at")
    list_filter = ("skill", "level", "is_published")
    search_fields = ("title", "slug", "vocab_word")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("skill", "sort_order")
    fieldsets = (
        (None, {"fields": ("skill", "level", "title", "slug", "sort_order", "is_published")}),
        ("Quiz (Reading / Listening)", {"fields": ("passage", "question_prompt", "options", "correct_index")}),
        ("Photo (Listening Part 1 / Writing photo-sentence)", {"fields": ("image_url", "image_credit")}),
        ("Writing", {"fields": ("writing_prompt", "min_words", "max_words")}),
        ("Vocabulary", {"fields": ("vocab_word", "vocab_ipa", "vocab_meaning", "vocab_example", "vocab_cefr")}),
    )


@admin.register(UserSkillLessonCompletion)
class UserSkillLessonCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "was_correct", "xp_earned", "completed_at")
    list_filter = ("was_correct", "lesson__skill")
    search_fields = ("user__username", "lesson__title")
    readonly_fields = ("completed_at",)


