from decimal import Decimal

from django.db import models
from django.utils import timezone

from .gamification import CEFR_LEVELS, ERROR_CATEGORIES, SM2_INITIAL_EASE_FACTOR


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
    streak_freezes = models.PositiveSmallIntegerField(default=0)
    last_freeze_consumed_at = models.DateTimeField(null=True, blank=True)
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
    # CEFR proficiency sub-level for this skill, computed from a rolling
    # accuracy window (see gamification.recompute_cefr_level) — not derived
    # from lesson-count/XP. None means "not yet assessed" (too little
    # graded history), not "beginner" — see stats_service for the fallback.
    cefr_level = models.CharField(
        max_length=2,
        choices=[(lvl, lvl) for lvl in CEFR_LEVELS],
        null=True,
        blank=True,
    )
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
        label = self.cefr_level or "unassessed"
        return f"{self.user.username} — {self.skill.name} ({label})"

    @property
    def progress_percent(self) -> int:
        """Catalog completion % — independent of CEFR proficiency assessment."""
        total = self.skill.total_lessons
        if total <= 0:
            return 0
        return min(100, round(self.lessons_completed * 100 / total))

    @property
    def status_label(self) -> str:
        return self.Status(self.status).label

    def sync_status(self) -> None:
        """Catalog-completion status only. CEFR level is recomputed
        separately — see stats_service.recompute_skill_cefr_level(), called
        after each graded interaction, not on every lesson-count change."""
        if self.lessons_completed <= 0:
            self.status = self.Status.NOT_STARTED
        elif self.progress_percent >= 100:
            self.status = self.Status.COMPLETED
        else:
            self.status = self.Status.IN_PROGRESS


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
    # Snapshot of the SkillLesson.level (1-15) this interaction was attempted
    # at, for CEFR band matching. Null for Speaking (no discrete lesson
    # ladder) and for rows predating CEFR sub-leveling — those are expected,
    # not missing data; see gamification.recompute_cefr_level.
    lesson_level = models.PositiveSmallIntegerField(null=True, blank=True)
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

    passage = models.TextField(blank=True, help_text="Reading: passage text. Listening: spoken-style transcript.")
    question_prompt = models.TextField(blank=True, help_text="Reading/Listening: question text.")
    options = models.JSONField(default=list, blank=True, help_text="Quiz answer options (list of strings).")
    correct_index = models.PositiveSmallIntegerField(default=0)

    # Stock photo for Listening Part 1 ("photograph") and Writing Q1-5
    # ("write a sentence based on the picture") style items. URL-based
    # (hotlinked to the source CDN), not an uploaded ImageField -- avoids
    # needing MEDIA_ROOT/serving infra this app doesn't have, and sidesteps
    # the same ephemeral-storage problem already documented for serverless
    # SQLite (see USING_EPHEMERAL_DATABASE in lisa/settings/base.py).
    # Licensed/royalty-free sources only (Unsplash, Pexels, etc.) -- never
    # scraped or copied from real ETS TOEIC materials.
    image_url = models.URLField(blank=True, help_text="Stock photo URL for photo-description items.")
    image_credit = models.CharField(
        max_length=200, blank=True, help_text="Attribution, e.g. 'Photo by Jane Doe on Unsplash'."
    )

    writing_prompt = models.TextField(blank=True, help_text="Writing: learner prompt.")
    min_words = models.PositiveSmallIntegerField(null=True, blank=True)
    max_words = models.PositiveSmallIntegerField(null=True, blank=True)

    vocab_word = models.CharField(max_length=80, blank=True)
    vocab_ipa = models.CharField(max_length=80, blank=True)
    vocab_meaning = models.TextField(blank=True)
    vocab_example = models.TextField(blank=True)
    vocab_cefr = models.CharField(max_length=4, blank=True, default="B2")

    # Listening: optional real video for this item. YouTube-embed URL, same
    # URL-string pattern as image_url above (no MEDIA_ROOT, no ephemeral-
    # storage problem) -- when blank, listening.js's client-side TTS reading
    # of `passage` is the fallback, same as it is for every item today.
    video_url = models.URLField(blank=True, help_text="YouTube embed URL for this listening item, if any.")

    # Denormalized "times practiced" counter, incremented on every submit
    # attempt (not just the first/counted-for-XP one) -- shown to all users
    # as a popularity signal, same idea as Parroto's per-lesson attempt count.
    times_practiced = models.PositiveIntegerField(default=0)

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


class UserVocabularyReviewState(models.Model):
    """
    SM-2 spaced-repetition state for one (user, vocabulary lesson) pair.

    `lesson` is a SkillLesson with skill.slug == "vocabulary" — content
    lives in the same staff-managed catalog as every other skill (Phase 2
    deliberately extends SkillLesson with review state rather than reviving
    the old standalone VocabularyWord model). Scoping to vocabulary lessons
    is enforced in the view layer, not a DB constraint.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vocabulary_review_states")
    lesson = models.ForeignKey(SkillLesson, on_delete=models.CASCADE, related_name="review_states")
    ease_factor = models.DecimalField(max_digits=3, decimal_places=2, default=SM2_INITIAL_EASE_FACTOR)
    interval_days = models.PositiveIntegerField(default=0)
    repetition_count = models.PositiveIntegerField(default=0)
    next_review_date = models.DateField(
        null=True,
        blank=True,
        help_text="Null means due immediately (never reviewed yet).",
    )
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [["user", "lesson"]]
        ordering = ["next_review_date"]

    def __str__(self):
        due = self.next_review_date.isoformat() if self.next_review_date else "new"
        return f"{self.user.username} · {self.lesson.vocab_word} (due {due})"


class TutorErrorPattern(models.Model):
    """
    Persistent, summarized recurring-error tracking per (user, skill) —
    Phase 3. Deliberately not raw transcript storage: `category` is a
    bounded taxonomy key (see gamification.ERROR_CATEGORIES) so a mistake
    detected across many sessions reinforces one row via get_or_create,
    never creates near-duplicate rows for re-phrased descriptions of the
    same underlying pattern. `skill` is general (not Speaking-specific) so
    another skill's tutor could plug into this same table later without a
    schema change — only the extraction trigger is Speaking-only today.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="error_patterns")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="error_patterns")
    category = models.CharField(max_length=40, choices=ERROR_CATEGORIES)
    example_note = models.TextField(
        blank=True,
        help_text="Latest illustrative snippet — overwritten on each reinforcement, not appended.",
    )
    occurrence_count = models.PositiveIntegerField(default=1)
    first_detected_at = models.DateTimeField(auto_now_add=True)
    last_detected_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Manually cleared (e.g. via admin) when a staff member judges this fixed. "
        "Reactivated automatically if the pattern is detected again.",
    )

    class Meta:
        unique_together = [["user", "skill", "category"]]
        ordering = ["-occurrence_count", "-last_detected_at"]

    def __str__(self):
        return f"{self.user.username} · {self.skill.slug} · {self.get_category_display()} ({self.occurrence_count}x)"


class MockExam(models.Model):
    """
    A full timed TOEIC-style practice test -- separate from SkillLesson's
    per-item catalog on purpose: SkillLesson is "one item, walked through
    sequentially, unique_together(user, lesson) caps it at one completion."
    An exam is "N items in one timed sitting, retaken freely" -- different
    enough shape (ordering within an exam, a shared timer/score across many
    questions, unlimited reattempts) that bolting it onto SkillLesson would
    fight its existing semantics rather than reuse them.

    Original questions only, TOEIC-format-inspired -- same rule already
    documented on SkillLesson.image_url: never scraped or copied from real
    ETS/Cambridge materials.
    """

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    time_limit_minutes = models.PositiveSmallIntegerField(default=25)
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title

    @property
    def question_count(self) -> int:
        return self.questions.count()


class MockExamQuestion(models.Model):
    SECTION_CHOICES = [("listening", "Listening"), ("reading", "Reading")]

    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="questions")
    section = models.CharField(max_length=20, choices=SECTION_CHOICES)
    order = models.PositiveIntegerField(default=0)

    # Listening: spoken-style transcript, read client-side via the same
    # speechSynthesis TTS as SkillLesson.passage (see listening.js). Reading:
    # the passage text itself.
    passage = models.TextField(blank=True)
    question_prompt = models.TextField()
    options = models.JSONField(default=list)
    correct_index = models.PositiveSmallIntegerField(default=0)
    explanation = models.TextField(
        blank=True, help_text="Shown on the results page under this question, right or wrong."
    )

    image_url = models.URLField(blank=True)
    image_credit = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["exam", "order", "id"]

    def __str__(self):
        return f"{self.exam.title} · Q{self.order} · {self.section}"


class MockExamAttempt(models.Model):
    """One timed sitting of a MockExam. Deliberately no unique_together on
    (user, exam) -- unlike UserSkillLessonCompletion, retaking an exam is
    the whole point, and `MockExam.objects.filter(...).count()`-style
    queries over this table are what a per-exam "times taken" counter reads
    (see stats_service.mock_exam_attempt_counts)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_attempts")
    exam = models.ForeignKey(MockExam, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    total_questions = models.PositiveIntegerField()
    correct_count = models.PositiveIntegerField(default=0)
    score_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    # {"<question_id>": <selected_index>} -- snapshot of what was picked,
    # so the results page can show right/wrong per question without asking
    # the client to resubmit its own answers.
    answers = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user.username} · {self.exam.title} · {self.started_at:%Y-%m-%d %H:%M}"
