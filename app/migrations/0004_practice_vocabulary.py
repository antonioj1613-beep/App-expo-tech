# Generated manually for stats migration

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Avg, Sum


def backfill_practice_sessions(apps, schema_editor):
    SpeakingSession = apps.get_model("app", "SpeakingSession")
    PracticeSession = apps.get_model("app", "PracticeSession")
    Skill = apps.get_model("app", "Skill")
    UserProfile = apps.get_model("app", "UserProfile")

    speaking_skill = Skill.objects.filter(slug="speaking").first()
    if not speaking_skill:
        return

    user_ids = set()
    for session in SpeakingSession.objects.all().iterator():
        PracticeSession.objects.create(
            user_id=session.user_id,
            skill_id=speaking_skill.id,
            xp_earned=session.xp_earned,
            accuracy_score=session.accuracy_score,
            duration_seconds=session.duration_seconds,
            created_at=session.created_at,
        )
        user_ids.add(session.user_id)

    for user_id in user_ids:
        sessions = PracticeSession.objects.filter(user_id=user_id)
        agg = sessions.aggregate(
            total_xp=Sum("xp_earned"),
            avg_accuracy=Avg("accuracy_score"),
            total_seconds=Sum("duration_seconds"),
        )
        profile, _ = UserProfile.objects.get_or_create(user_id=user_id)
        profile.total_xp = agg["total_xp"] or 0
        profile.avg_accuracy = agg["avg_accuracy"]
        seconds = agg["total_seconds"] or 0
        from decimal import Decimal

        profile.study_hours = (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.01"))
        profile.save(
            update_fields=["total_xp", "avg_accuracy", "study_hours", "updated_at"]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0003_progress_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="VocabularyWord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("word", models.CharField(max_length=80)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("ipa", models.CharField(blank=True, max_length=80)),
                ("meaning", models.TextField()),
                ("example", models.TextField(blank=True)),
                ("level", models.CharField(default="B2", max_length=4)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "word"],
            },
        ),
        migrations.CreateModel(
            name="PracticeSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("xp_earned", models.PositiveIntegerField(default=0)),
                (
                    "accuracy_score",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
                ),
                ("duration_seconds", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "skill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="practice_sessions",
                        to="app.skill",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="practice_sessions",
                        to="app.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="UserVocabularyMastery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("correct_count", models.PositiveSmallIntegerField(default=0)),
                ("mastered_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vocabulary_mastery",
                        to="app.user",
                    ),
                ),
                (
                    "word",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_mastery",
                        to="app.vocabularyword",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
                "unique_together": {("user", "word")},
            },
        ),
        migrations.AddIndex(
            model_name="practicesession",
            index=models.Index(fields=["user", "created_at"], name="app_practic_user_id_created_idx"),
        ),
        migrations.AddIndex(
            model_name="practicesession",
            index=models.Index(fields=["user", "skill", "created_at"], name="app_practic_user_skill_created_idx"),
        ),
        migrations.RunPython(backfill_practice_sessions, migrations.RunPython.noop),
    ]
