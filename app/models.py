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


class PracticeSession(models.Model):
    """
    Unified practice record for dashboard/statistics aggregation.

    Speaking keeps SpeakingSession for transcripts; every completed practice
  activity also writes a PracticeSession row.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="practice_sessions")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="practice_sessions")
    xp_earned = models.PositiveIntegerField(default=0)
    accuracy_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    duration_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "skill", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} · {self.skill.slug} · {self.xp_earned} XP"


class VocabularyWord(models.Model):
    """Reference vocabulary item — content seeded via management command."""

    word = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    ipa = models.CharField(max_length=80, blank=True)
    meaning = models.TextField()
    example = models.TextField(blank=True)
    level = models.CharField(max_length=4, default="B2")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "word"]

    def __str__(self):
        return self.word


class UserVocabularyMastery(models.Model):
    """Per-user mastery for a vocabulary word (words_learned when mastered)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vocabulary_mastery")
    word = models.ForeignKey(VocabularyWord, on_delete=models.CASCADE, related_name="user_mastery")
    correct_count = models.PositiveSmallIntegerField(default=0)
    mastered_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["user", "word"]]
        ordering = ["-updated_at"]

    def __str__(self):
        status = "mastered" if self.mastered_at else f"{self.correct_count} correct"
        return f"{self.user.username} · {self.word.word} ({status})"

    @property
    def is_mastered(self) -> bool:
        return self.mastered_at is not None


class ReadingLesson(models.Model):
    """Deprecated — use SkillLesson. Kept until migration completes."""

    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    passage = models.TextField()
    question_prompt = models.TextField()
    options = models.JSONField(help_text="List of answer option strings.")
    correct_index = models.PositiveSmallIntegerField()
    level = models.PositiveSmallIntegerField(default=1)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


STAFF_SKILL_SLUGS = ("listening", "reading", "writing", "vocabulary")


class SkillLesson(models.Model):
    """
    Lesson content for Listening, Reading, Writing, and Vocabulary.
    Created via the staff Lesson Builder (/staff/lesson-builder/) or Django admin.
    """

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="lessons",
        limit_choices_to={"slug__in": STAFF_SKILL_SLUGS},
    )
    level = models.PositiveSmallIntegerField(
        default=1,
        help_text="Level number (1–15) within this skill path.",
    )
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    passage = models.TextField(blank=True, help_text="Reading: passage text.")
    question_prompt = models.TextField(blank=True, help_text="Reading/Listening: question text.")
    options = models.JSONField(default=list, blank=True, help_text="Quiz answer options (list of strings).")
    correct_index = models.PositiveSmallIntegerField(default=0)

    writing_prompt = models.TextField(blank=True, help_text="Writing: learner prompt.")
    min_words = models.PositiveSmallIntegerField(null=True, blank=True)
    max_words = models.PositiveSmallIntegerField(null=True, blank=True)

    vocab_word = models.CharField(max_length=80, blank=True)
    vocab_ipa = models.CharField(max_length=80, blank=True)
    vocab_meaning = models.TextField(blank=True)
    vocab_example = models.TextField(blank=True)
    vocab_cefr = models.CharField(max_length=4, blank=True, default="B2")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["skill", "sort_order", "id"]
        unique_together = [["skill", "slug"]]

    def __str__(self):
        return f"{self.skill.name} · L{self.level} · {self.title}"

    @property
    def skill_slug(self) -> str:
        return self.skill.slug


class UserSkillLessonCompletion(models.Model):
    """Tracks first completion of a skill lesson (prevents duplicate XP)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lesson_completions")
    lesson = models.ForeignKey(SkillLesson, on_delete=models.CASCADE, related_name="completions")
    was_correct = models.BooleanField(null=True, blank=True)
    xp_earned = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user", "lesson"]]
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.user.username} · {self.lesson}"


class UserReadingLessonCompletion(models.Model):
    """Tracks first completion of a reading lesson (prevents duplicate XP)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reading_completions")
    lesson = models.ForeignKey(ReadingLesson, on_delete=models.CASCADE, related_name="completions")
    was_correct = models.BooleanField()
    xp_earned = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user", "lesson"]]
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.user.username} · {self.lesson.slug}"
