from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import STAFF_SKILL_SLUGS, SkillLesson, User, UserProfile, UserSkillProgress
from .stats_service import ensure_user_skill_progress, seed_skills


@receiver(post_save, sender=User)
def setup_new_user(sender, instance, created, **kwargs):
    if not created:
        return
    UserProfile.objects.get_or_create(user=instance)
    seed_skills()
    ensure_user_skill_progress(instance)


@receiver(post_save, sender=SkillLesson)
@receiver(post_delete, sender=SkillLesson)
def sync_skill_lesson_count(sender, instance, **kwargs):
    """Keep Skill.total_lessons aligned with published lesson count for staff-managed skills."""
    skill = instance.skill
    if skill.slug not in STAFF_SKILL_SLUGS:
        return
    count = SkillLesson.objects.filter(skill=skill, is_published=True).count()
    if skill.total_lessons != count:
        skill.total_lessons = count
        skill.save(update_fields=["total_lessons"])

    for progress in UserSkillProgress.objects.filter(skill=skill):
        progress.sync_status_and_level()
        progress.save(update_fields=["status", "level"])

