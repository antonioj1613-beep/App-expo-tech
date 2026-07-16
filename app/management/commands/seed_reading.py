from django.core.management.base import BaseCommand
from django.utils.text import slugify

from app.models import Skill, SkillLesson

READING_SEED = [
    {
        "title": "Remote work policy email",
        "passage": """From: Sarah Chen, HR Director
To: All Employees
Subject: New Remote Work Guidelines

Dear team,

Following last quarter's feedback, we are rolling out an updated remote work policy that takes effect on March 1st. Each team will be required to coordinate at least two in-office days per week, with the specific days chosen by the team lead in collaboration with each member.

We believe this hybrid model best balances flexibility with collaboration. Managers will host a kickoff session next week to discuss expectations and answer your questions.

Best,
Sarah""",
        "question_prompt": "What is the main purpose of the email?",
        "options": [
            "To request feedback on employees",
            "To notify employees of a new remote work policy",
            "To introduce a new supervisor",
            "To announce a salary adjustment",
        ],
        "correct_index": 1,
        "level": 1,
    },
    {
        "title": "Library hours notice",
        "passage": """Notice: City Central Library

Starting April 15, the library will extend weekend hours. Saturday hours will be 9:00 a.m. to 8:00 p.m., and Sunday hours will be 10:00 a.m. to 6:00 p.m. Weekday hours remain unchanged.

The change responds to community requests for more evening access. Study rooms can be booked online up to one week in advance.""",
        "question_prompt": "Why are the library hours changing?",
        "options": [
            "To reduce staff costs",
            "Because of community requests for more access",
            "To prepare for a building renovation",
            "To match school holiday schedules",
        ],
        "correct_index": 1,
        "level": 1,
    },
    {
        "title": "Team project update",
        "passage": """Hi everyone,

Quick update on the Atlas project: we completed user testing last Friday and received positive feedback on the onboarding flow. The main issue reported was slow load times on older phones.

Engineering will prioritize performance fixes this sprint. Design will revise two screens based on tester comments. Our target launch date is still May 20.

Thanks,
Jordan""",
        "question_prompt": "What problem did user testing reveal?",
        "options": [
            "Confusing navigation menus",
            "Slow load times on older phones",
            "Missing payment options",
            "Poor color contrast",
        ],
        "correct_index": 1,
        "level": 2,
    },
    {
        "title": "Travel advisory",
        "passage": """Travel Advisory — Coastal Region

Heavy rainfall is expected through Thursday. Local authorities advise avoiding non-essential travel on Route 9 after 6 p.m. Ferry services may be delayed or cancelled with short notice.

Residents should monitor official weather channels and keep emergency kits ready. Schools in the coastal district will announce closures by 5 a.m. each morning.""",
        "question_prompt": "What should residents do according to the advisory?",
        "options": [
            "Evacuate immediately",
            "Monitor weather channels and prepare emergency kits",
            "Cancel all work meetings",
            "Travel on Route 9 before noon only",
        ],
        "correct_index": 1,
        "level": 2,
    },
    {
        "title": "Museum exhibition",
        "passage": """New Exhibition: "Voices of the Harbor"

The Maritime Museum opens a new exhibition on June 3 featuring oral histories from dockworkers and shipbuilders. Guided tours run every hour from 11 a.m. to 4 p.m.

Admission is included with a standard ticket. Members enter free. The exhibition will remain open until September 30.""",
        "question_prompt": "Who can enter the exhibition without paying extra?",
        "options": [
            "Only children under 12",
            "Anyone with a guided tour ticket",
            "Museum members",
            "Local school groups only",
        ],
        "correct_index": 2,
        "level": 3,
    },
    {
        "title": "Community garden signup",
        "passage": """Community Garden — Spring Registration

Plots are available starting March 10 for residents of Oak Street and nearby blocks. Each plot costs $25 for the season and includes shared tool access and weekly watering on Tuesdays.

New gardeners must attend a 30-minute orientation on March 8 at 6 p.m. in the community center. Sign up online or at the front desk by March 5.""",
        "question_prompt": "What must new gardeners do before getting a plot?",
        "options": [
            "Pay $25 at the front desk only",
            "Attend an orientation session",
            "Live on Oak Street for one year",
            "Bring their own gardening tools",
        ],
        "correct_index": 1,
        "level": 4,
    },
    {
        "title": "Fitness class schedule",
        "passage": """Riverside Gym — April Class Update

Beginning April 1, morning yoga moves to 7:00 a.m. on Mondays and Wednesdays. Evening spin classes remain at 6:30 p.m. on Tuesdays and Thursdays.

Members can book classes through the mobile app up to 48 hours in advance. Non-members may join one trial class per month with prior registration.""",
        "question_prompt": "How can members reserve a class?",
        "options": [
            "By calling the front desk only",
            "Through the mobile app",
            "By arriving 30 minutes early",
            "By emailing the instructor directly",
        ],
        "correct_index": 1,
        "level": 5,
    },
]


class Command(BaseCommand):
    help = "Seed reading lessons into SkillLesson (hybrid content model)."

    def handle(self, *args, **options):
        reading_skill = Skill.objects.filter(slug="reading").first()
        if not reading_skill:
            self.stderr.write(self.style.ERROR("Reading skill not found — run seed_skills first."))
            return

        created = 0
        for order, row in enumerate(READING_SEED, start=1):
            slug = slugify(row["title"])[:80]
            _, is_new = SkillLesson.objects.update_or_create(
                skill=reading_skill,
                slug=slug,
                defaults={**row, "sort_order": order, "is_published": True},
            )
            if is_new:
                created += 1
        total = SkillLesson.objects.filter(skill=reading_skill).count()
        self.stdout.write(self.style.SUCCESS(f"Reading seed complete: {total} lesson(s), {created} new."))
