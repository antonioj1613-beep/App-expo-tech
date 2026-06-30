from django.core.management.base import BaseCommand

from app.models import User
from app.stats_service import ensure_user_skill_progress, seed_skills


class Command(BaseCommand):
    help = "Seed the five skills and ensure every user has progress rows."

    def handle(self, *args, **options):
        skills = seed_skills()
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(skills)} skills:"))
        for skill in skills:
            self.stdout.write(f"  · {skill.name}: {skill.total_lessons} lessons")

        user_count = 0
        for user in User.objects.all():
            ensure_user_skill_progress(user)
            user_count += 1

        self.stdout.write(self.style.SUCCESS(f"Ensured skill progress for {user_count} user(s)."))
