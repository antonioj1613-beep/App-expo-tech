from decimal import Decimal

from django.db import models
from django.utils import timezone


class User(models.Model):
    """App user account stored in the `users` table."""

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return self.username


class UserProfile(models.Model):
    """Extended learner profile linked to a user account."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    streak_days = models.PositiveIntegerField(default=0)
    total_xp = models.PositiveIntegerField(default=0)
    avg_accuracy = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cached average accuracy (%) across scored sessions.",
    )
    study_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Cumulative practice time in hours.",
    )
    words_learned = models.PositiveIntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    native_language = models.CharField(max_length=50, default="English")
    app_language = models.CharField(max_length=50, default="English")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} profile"

    @property
    def current_streak(self) -> int:
        return self.streak_days


class Skill(models.Model):
    """Reference skill with total lesson count for progress tracking."""

    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=30, unique=True)
    total_lessons = models.PositiveIntegerField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.total_lessons} lessons)"


class UserSkillProgress(models.Model):
    """Per-user progress for a single skill."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skill_progress")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="user_progress")
    level = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    lessons_completed = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["skill__name"]
        unique_together = [["user", "skill"]]

    def __str__(self):
        return f"{self.user.username} — {self.skill.name} (Lv {self.level})"

    @property
    def progress_percent(self) -> int:
        total = self.skill.total_lessons
        if total <= 0:
            return 0
        return min(100, round(self.lessons_completed * 100 / total))

    @property
    def status_label(self) -> str:
        return self.Status(self.status).label

    def sync_status_and_level(self, max_level: int = 15) -> None:
        percent = self.progress_percent
        if self.lessons_completed <= 0:
            self.status = self.Status.NOT_STARTED
            self.level = 1
        elif percent >= 100:
            self.status = self.Status.COMPLETED
            self.level = max_level
        else:
            self.status = self.Status.IN_PROGRESS
            lessons_per_level = max(1, self.skill.total_lessons // max_level)
            self.level = min(max_level, max(1, self.lessons_completed // lessons_per_level + 1))


class SpeakingSession(models.Model):
    """A completed voice-practice session with Miles or Maya."""

    class Tutor(models.TextChoices):
        MILES = "Miles", "Miles"
        MAYA = "Maya", "Maya"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="speaking_sessions")
    tutor = models.CharField(max_length=10, choices=Tutor.choices, default=Tutor.MILES)
    transcript = models.JSONField(
        default=list,
        help_text="List of {role, content} chat turns.",
    )
    accuracy_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Session accuracy (%) — average of per-turn scores.",
    )
    xp_earned = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} · {self.tutor} · {self.created_at:%Y-%m-%d %H:%M}"
