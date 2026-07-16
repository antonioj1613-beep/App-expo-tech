from django.core.management.base import BaseCommand
from django.utils.text import slugify

from app.models import Skill, SkillLesson

WRITING_SEED = [
    {
        "title": "Your morning routine",
        "writing_prompt": "Write 2–3 sentences describing what you usually do in the morning before work or school.",
        "min_words": 20,
        "max_words": 80,
        "level": 1,
    },
    {
        "title": "Favorite meal",
        "writing_prompt": "Describe your favorite meal. What is it, where do you eat it, and why do you enjoy it?",
        "min_words": 30,
        "max_words": 100,
        "level": 2,
    },
    {
        "title": "A place you visited",
        "writing_prompt": "Write a short paragraph about a city or town you have visited. Include what you saw and what you liked most.",
        "min_words": 50,
        "max_words": 120,
        "level": 3,
    },
    {
        "title": "Email to a colleague",
        "writing_prompt": "Write a polite email to a colleague asking to reschedule a meeting from Thursday to Friday afternoon. Explain briefly why you need the change.",
        "min_words": 60,
        "max_words": 150,
        "level": 4,
    },
    {
        "title": "Remote work opinion",
        "writing_prompt": "Do you think remote work improves productivity? Write a short opinion paragraph with at least one reason supporting your view.",
        "min_words": 80,
        "max_words": 180,
        "level": 5,
    },
]


class Command(BaseCommand):
    help = "Seed writing lessons into SkillLesson."

    def handle(self, *args, **options):
        writing_skill = Skill.objects.filter(slug="writing").first()
        if not writing_skill:
            self.stderr.write(self.style.ERROR("Writing skill not found — run seed_skills first."))
            return

        created = 0
        for order, row in enumerate(WRITING_SEED, start=1):
            slug = slugify(row["title"])[:80]
            _, is_new = SkillLesson.objects.update_or_create(
                skill=writing_skill,
                slug=slug,
                defaults={**row, "sort_order": order, "is_published": True},
            )
            if is_new:
                created += 1
        total = SkillLesson.objects.filter(skill=writing_skill).count()
        self.stdout.write(self.style.SUCCESS(f"Writing seed complete: {total} lesson(s), {created} new."))
