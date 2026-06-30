from django.contrib import admin

from .models import (
    PracticeSession,
    ReadingLesson,
    Skill,
    SkillLesson,
    SpeakingSession,
    User,
    UserProfile,
    UserReadingLessonCompletion,
    UserSkillLessonCompletion,
    UserSkillProgress,
    UserVocabularyMastery,
    VocabularyWord,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "created_at")
    search_fields = ("username", "email")
    readonly_fields = ("created_at",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "streak_days",
        "total_xp",
        "avg_accuracy",
        "study_hours",
        "words_learned",
        "last_active_date",
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
    list_display = ("user", "skill", "level", "status", "lessons_completed", "last_updated")
    list_filter = ("status", "skill")
    search_fields = ("user__username",)
    readonly_fields = ("last_updated",)


@admin.register(SpeakingSession)
class SpeakingSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "tutor", "xp_earned", "accuracy_score", "duration_seconds", "created_at")
    list_filter = ("tutor",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "xp_earned", "accuracy_score", "duration_seconds", "created_at")
    list_filter = ("skill",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)


@admin.register(VocabularyWord)
class VocabularyWordAdmin(admin.ModelAdmin):
    list_display = ("word", "level", "sort_order")
    search_fields = ("word", "meaning")
    prepopulated_fields = {"slug": ("word",)}


@admin.register(UserVocabularyMastery)
class UserVocabularyMasteryAdmin(admin.ModelAdmin):
    list_display = ("user", "word", "correct_count", "mastered_at", "updated_at")
    list_filter = ("mastered_at",)
    search_fields = ("user__username", "word__word")
    readonly_fields = ("updated_at",)


@admin.register(ReadingLesson)
class ReadingLessonAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "level", "sort_order", "correct_index")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("sort_order",)

    def has_module_permission(self, request):
        return False


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
        ("Writing", {"fields": ("writing_prompt", "min_words", "max_words")}),
        ("Vocabulary", {"fields": ("vocab_word", "vocab_ipa", "vocab_meaning", "vocab_example", "vocab_cefr")}),
    )


@admin.register(UserSkillLessonCompletion)
class UserSkillLessonCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "was_correct", "xp_earned", "completed_at")
    list_filter = ("was_correct", "lesson__skill")
    search_fields = ("user__username", "lesson__title")
    readonly_fields = ("completed_at",)


@admin.register(UserReadingLessonCompletion)
class UserReadingLessonCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "lesson", "was_correct", "xp_earned", "completed_at")
    list_filter = ("was_correct",)
    search_fields = ("user__username", "lesson__title")
    readonly_fields = ("completed_at",)
