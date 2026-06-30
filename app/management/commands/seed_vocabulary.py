from django.core.management.base import BaseCommand
from django.utils.text import slugify

from app.models import VocabularyWord

VOCABULARY_SEED = [
    {
        "word": "Ephemeral",
        "ipa": "/ɪˈfɛm(ə)rəl/",
        "meaning": "Lasting for a very short time.",
        "example": "The beauty of the sunset is ephemeral.",
        "level": "C1",
    },
    {
        "word": "Resilient",
        "ipa": "/rɪˈzɪlɪənt/",
        "meaning": "Able to recover quickly from difficulty.",
        "example": "She remained resilient throughout the project.",
        "level": "B2",
    },
    {
        "word": "Pragmatic",
        "ipa": "/præɡˈmætɪk/",
        "meaning": "Dealing with things sensibly and realistically.",
        "example": "A pragmatic approach works best.",
        "level": "C1",
    },
    {
        "word": "Ubiquitous",
        "ipa": "/juːˈbɪkwɪtəs/",
        "meaning": "Present, appearing, or found everywhere.",
        "example": "Smartphones are ubiquitous today.",
        "level": "C2",
    },
    {
        "word": "Candid",
        "ipa": "/ˈkændɪd/",
        "meaning": "Truthful and straightforward.",
        "example": "I appreciate your candid feedback.",
        "level": "B2",
    },
    {
        "word": "Meticulous",
        "ipa": "/mɪˈtɪkjʊləs/",
        "meaning": "Showing great attention to detail.",
        "example": "He is meticulous in his work.",
        "level": "C1",
    },
]


class Command(BaseCommand):
    help = "Seed vocabulary reference words (hybrid content model)."

    def handle(self, *args, **options):
        count = 0
        for order, row in enumerate(VOCABULARY_SEED, start=1):
            slug = slugify(row["word"])
            _, created = VocabularyWord.objects.update_or_create(
                slug=slug,
                defaults={**row, "sort_order": order},
            )
            if created:
                count += 1
        total = VocabularyWord.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Vocabulary seed complete: {total} word(s), {count} new."))
