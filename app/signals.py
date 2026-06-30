from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User, UserProfile
from .stats_service import ensure_user_skill_progress, seed_skills


@receiver(post_save, sender=User)
def setup_new_user(sender, instance, created, **kwargs):
    if not created:
        return
    UserProfile.objects.get_or_create(user=instance)
    seed_skills()
    ensure_user_skill_progress(instance)
