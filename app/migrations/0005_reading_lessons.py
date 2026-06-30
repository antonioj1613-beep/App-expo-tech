# Generated manually for Reading lessons

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0004_practice_vocabulary"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingLesson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("title", models.CharField(max_length=120)),
                ("passage", models.TextField()),
                ("question_prompt", models.TextField()),
                ("options", models.JSONField(help_text="List of answer option strings.")),
                ("correct_index", models.PositiveSmallIntegerField()),
                ("level", models.PositiveSmallIntegerField(default=1)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.CreateModel(
            name="UserReadingLessonCompletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("was_correct", models.BooleanField()),
                ("xp_earned", models.PositiveIntegerField(default=0)),
                ("completed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lesson",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="completions",
                        to="app.readinglesson",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reading_completions",
                        to="app.user",
                    ),
                ),
            ],
            options={
                "ordering": ["-completed_at"],
                "unique_together": {("user", "lesson")},
            },
        ),
    ]
