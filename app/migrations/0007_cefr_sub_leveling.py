# Phase 1: per-skill CEFR sub-leveling.
#
# UserSkillProgress.level (int 1-15, lesson-count derived) is replaced by
# cefr_level (CharField A1-C2, rolling-accuracy derived — see
# gamification.recompute_cefr_level). This migration backfills existing
# rows non-destructively before dropping the old column:
#
# - For a skill the user has actually practiced (lessons_completed > 0),
#   the old lesson-count level is mapped through the same 1-15 -> CEFR band
#   table used going forward (gamification.LESSON_LEVEL_TO_CEFR_BAND),
#   inlined here per Django migration convention (migrations should not
#   import app code that can change independently of migration history).
#   This is a one-time starting estimate, not a measurement — it gets
#   refined by real rolling-window data as the user keeps practicing.
# - For a skill never touched (lessons_completed == 0 — the common case,
#   since `level` defaulted to 1 for everyone regardless of activity),
#   cefr_level is set to None ("not yet assessed") rather than mapping the
#   meaningless default of 1 -> A1.
#
# No row is deleted and no user is silently reset; every row gets either a
# real backfilled estimate or an explicit "not yet assessed" state.
from django.db import migrations, models

LESSON_LEVEL_TO_CEFR_BAND = {
    1: "A1", 2: "A1",
    3: "A2", 4: "A2",
    5: "B1", 6: "B1", 7: "B1",
    8: "B2", 9: "B2",
    10: "C1", 11: "C1", 12: "C1",
    13: "C2", 14: "C2", 15: "C2",
}


def backfill_cefr_levels(apps, schema_editor):
    UserSkillProgress = apps.get_model("app", "UserSkillProgress")
    for progress in UserSkillProgress.objects.all():
        if progress.lessons_completed > 0:
            old_level = max(1, min(15, progress.level or 1))
            progress.cefr_level = LESSON_LEVEL_TO_CEFR_BAND[old_level]
        else:
            progress.cefr_level = None
        progress.save(update_fields=["cefr_level"])


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0006_skill_lessons'),
    ]

    operations = [
        migrations.AddField(
            model_name='practicesession',
            name='lesson_level',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userskillprogress',
            name='cefr_level',
            field=models.CharField(blank=True, choices=[('A1', 'A1'), ('A2', 'A2'), ('B1', 'B1'), ('B2', 'B2'), ('C1', 'C1'), ('C2', 'C2')], max_length=2, null=True),
        ),
        migrations.RunPython(backfill_cefr_levels, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='userskillprogress',
            name='level',
        ),
    ]
