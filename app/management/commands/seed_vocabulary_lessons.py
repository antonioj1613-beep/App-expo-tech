from django.core.management.base import BaseCommand
from django.utils.text import slugify

from app.models import Skill, SkillLesson

VOCABULARY_LESSON_SEED = [
    {
        "title": "Friend",
        "vocab_word": "Friend",
        "vocab_ipa": "/frend/",
        "vocab_meaning": "A person you know well and like.",
        "vocab_example": "She met her best friend in high school.",
        "vocab_cefr": "A1",
        "level": 1,
    },
    {
        "title": "Travel",
        "vocab_word": "Travel",
        "vocab_ipa": "/ˈtrævəl/",
        "vocab_meaning": "To go from one place to another, especially over a long distance.",
        "vocab_example": "They love to travel together during the summer.",
        "vocab_cefr": "A1",
        "level": 2,
    },
    {
        "title": "Discuss",
        "vocab_word": "Discuss",
        "vocab_ipa": "/dɪˈskʌs/",
        "vocab_meaning": "To talk about something with another person or group.",
        "vocab_example": "Let's discuss the plan before the meeting.",
        "vocab_cefr": "A2",
        "level": 3,
    },
    {
        "title": "Achieve",
        "vocab_word": "Achieve",
        "vocab_ipa": "/əˈtʃiːv/",
        "vocab_meaning": "To successfully reach a goal or result.",
        "vocab_example": "He worked hard to achieve his certification.",
        "vocab_cefr": "A2",
        "level": 4,
    },
    {
        "title": "Recommend",
        "vocab_word": "Recommend",
        "vocab_ipa": "/ˌrɛkəˈmɛnd/",
        "vocab_meaning": "To suggest that someone should do or try something.",
        "vocab_example": "I recommend this book for beginners.",
        "vocab_cefr": "B1",
        "level": 5,
    },
]


class Command(BaseCommand):
    help = "Seed vocabulary lessons into SkillLesson."

    def handle(self, *args, **options):
        vocabulary_skill = Skill.objects.filter(slug="vocabulary").first()
        if not vocabulary_skill:
            self.stderr.write(self.style.ERROR("Vocabulary skill not found — run seed_skills first."))
            return

        created = 0
        for order, row in enumerate(VOCABULARY_LESSON_SEED, start=1):
            slug = slugify(row["title"])[:80]
            _, is_new = SkillLesson.objects.update_or_create(
                skill=vocabulary_skill,
                slug=slug,
                defaults={**row, "sort_order": order, "is_published": True},
            )
            if is_new:
                created += 1
        total = SkillLesson.objects.filter(skill=vocabulary_skill).count()
        self.stdout.write(self.style.SUCCESS(f"Vocabulary lessons seed complete: {total} lesson(s), {created} new."))
