from django.contrib import admin

from .models import Skill, SpeakingSession, User, UserProfile, UserSkillProgress


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
