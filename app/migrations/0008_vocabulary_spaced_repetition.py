# Phase 2: SM-2 spaced repetition for vocabulary.
#
# Drops VocabularyWord / UserVocabularyMastery — the Phase 0 audit found
# these tables disconnected from the live Lesson Builder content pipeline
# and confirmed empty (0 rows in both) with no code path that ever wrote to
# them (record_vocabulary_answer() was defined but never called anywhere).
# Nothing to backfill or preserve here, unlike the CEFR migration before
# this one. Review state now lives on UserVocabularyReviewState, scoped to
# the SkillLesson catalog (skill=vocabulary) instead of a standalone word
# list — Phase 0 explicitly chose not to run two parallel vocabulary
# sources.
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0007_cefr_sub_leveling'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserVocabularyReviewState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ease_factor', models.DecimalField(decimal_places=2, default=Decimal('2.5'), max_digits=3)),
                ('interval_days', models.PositiveIntegerField(default=0)),
                ('repetition_count', models.PositiveIntegerField(default=0)),
                ('next_review_date', models.DateField(blank=True, help_text='Null means due immediately (never reviewed yet).', null=True)),
                ('last_reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('lesson', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_states', to='app.skilllesson')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vocabulary_review_states', to='app.user')),
            ],
            options={
                'ordering': ['next_review_date'],
                'unique_together': {('user', 'lesson')},
            },
        ),
        migrations.DeleteModel(
            name='UserVocabularyMastery',
        ),
        migrations.DeleteModel(
            name='VocabularyWord',
        ),
    ]
