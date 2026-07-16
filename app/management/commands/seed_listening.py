from django.core.management.base import BaseCommand
from django.utils.text import slugify

from app.models import Skill, SkillLesson

LISTENING_SEED = [
    {
        "title": "Coffee shop order",
        "passage": """Barista: Good morning! What can I get for you today?
Customer: Hi, could I have a medium latte, please?
Barista: Sure. Would you like that hot or iced?
Customer: Hot, please. And can I add an extra shot?
Barista: Of course. That'll be four fifty.
Customer: Here you go. Thanks!""",
        "question_prompt": "What drink does the customer order?",
        "options": [
            "A small cappuccino",
            "A medium latte with an extra shot",
            "An iced tea",
            "A large hot chocolate",
        ],
        "correct_index": 1,
        "level": 1,
    },
    {
        "title": "Asking for directions",
        "passage": """Tourist: Excuse me, how do I get to the train station from here?
Local: Go straight for two blocks, then turn left at the traffic lights.
Tourist: Is it a long walk?
Local: About ten minutes. You'll see the station on your right after the bridge.
Tourist: Perfect, thank you so much!""",
        "question_prompt": "Where should the tourist turn?",
        "options": [
            "Right at the bridge",
            "Left at the traffic lights",
            "Right at the coffee shop",
            "Left after the station",
        ],
        "correct_index": 1,
        "level": 2,
    },
    {
        "title": "Doctor's appointment",
        "passage": """Receptionist: Good afternoon, Dr. Patel's office. How can I help?
Patient: Hi, I'd like to book an appointment. I've had a sore throat for three days.
Receptionist: We have an opening tomorrow at 2:30 p.m. Does that work?
Patient: Yes, that's fine.
Receptionist: Great. Please bring your insurance card with you.""",
        "question_prompt": "Why is the patient calling?",
        "options": [
            "To cancel an appointment",
            "To request a prescription refill",
            "To book an appointment for a sore throat",
            "To ask about insurance coverage",
        ],
        "correct_index": 2,
        "level": 3,
    },
    {
        "title": "Job interview introduction",
        "passage": """Interviewer: Thanks for coming in today. Tell me a little about yourself.
Candidate: I'm a project coordinator with four years of experience in tech. I manage timelines and keep teams aligned.
Interviewer: What attracted you to this role?
Candidate: I enjoy solving problems and working with cross-functional teams. Your company's focus on learning really stood out to me.""",
        "question_prompt": "What is the candidate's current role?",
        "options": [
            "Software engineer",
            "Project coordinator",
            "Marketing manager",
            "Customer support lead",
        ],
        "correct_index": 1,
        "level": 4,
    },
    {
        "title": "Morning routine podcast",
        "passage": """Host: Welcome back to Daily Habits. Today we're talking about morning routines that actually stick.
Guest: The key is starting small. Even five minutes of stretching or journaling can set a positive tone for the day.
Host: So you don't need a two-hour ritual to see results?
Guest: Exactly. Consistency matters more than complexity.""",
        "question_prompt": "According to the guest, what matters most?",
        "options": [
            "Waking up before sunrise",
            "A two-hour morning ritual",
            "Consistency over complexity",
            "Avoiding all screen time",
        ],
        "correct_index": 2,
        "level": 5,
    },
]


class Command(BaseCommand):
    help = "Seed listening lessons into SkillLesson."

    def handle(self, *args, **options):
        listening_skill = Skill.objects.filter(slug="listening").first()
        if not listening_skill:
            self.stderr.write(self.style.ERROR("Listening skill not found — run seed_skills first."))
            return

        created = 0
        for order, row in enumerate(LISTENING_SEED, start=1):
            slug = slugify(row["title"])[:80]
            _, is_new = SkillLesson.objects.update_or_create(
                skill=listening_skill,
                slug=slug,
                defaults={**row, "sort_order": order, "is_published": True},
            )
            if is_new:
                created += 1
        total = SkillLesson.objects.filter(skill=listening_skill).count()
        self.stdout.write(self.style.SUCCESS(f"Listening seed complete: {total} lesson(s), {created} new."))
