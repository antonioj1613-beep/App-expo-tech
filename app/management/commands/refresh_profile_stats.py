from django.core.management.base import BaseCommand

from app.models import User
from app.stats_service import refresh_profile_stats


class Command(BaseCommand):
    help = "Recompute cached profile stats from practice sessions for all users."

    def handle(self, *args, **options):
        count = 0
        for user in User.objects.iterator():
            refresh_profile_stats(user)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Refreshed profile stats for {count} user(s)."))
