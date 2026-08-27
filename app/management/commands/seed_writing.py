"""
Seed the full 15-level TOEIC writing catalog into SkillLesson.

Replaces the entire existing Writing catalog on every run (--replace
semantics, always on), mirroring seed_vocabulary_lessons.py: deletes all
SkillLesson rows for skill=writing first, then recreates the full 34-item
set below via a per-item create() loop (keeps the post_save signal that
syncs Skill.total_lessons — see signals.sync_skill_lesson_count).

Task-type progression: photo-sentence + simple description (L1-4) -> email
response (L5-9, overlapping with opinion paragraphs at L7-9) -> opinion
essay (L10-15). The 3 photo-sentence items (L1-L3) resolve `image_query`
(popped before create()) to a real stock photo via
stock_image_service.get_stock_image() when PEXELS_API_KEY is set; left
blank otherwise (no fabricated URL).

Level -> CEFR band matches gamification.LESSON_LEVEL_TO_CEFR_BAND exactly:
1-2 A1, 3-4 A2, 5-7 B1, 8-9 B2, 10-12 C1, 13-15 C2.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from app.models import Skill, SkillLesson
from app.stock_image_service import get_stock_image

WRITING_LESSON_SEED = [
    # --- Level 1 -- A1 -----------------------------------------------------
    {"title": "Your morning routine", "writing_prompt": "Write 2–3 sentences describing what you usually do in the morning before work or school.", "min_words": 15, "max_words": 40, "level": 1},
    {"title": "Your family", "writing_prompt": "Write a few sentences describing your family. Who do you live with?", "min_words": 15, "max_words": 40, "level": 1},
    {"title": "At the office", "writing_prompt": "Look at the picture. Write ONE sentence about the picture using the words 'woman' and 'computer'. You may change the word forms and use the words in any order.",
     "min_words": 5, "max_words": 20, "level": 1, "image_query": "woman working at computer in office"},

    # --- Level 2 -- A1 -----------------------------------------------------
    {"title": "Favorite meal", "writing_prompt": "Describe your favorite meal. What is it, where do you eat it, and why do you enjoy it?", "min_words": 15, "max_words": 40, "level": 2},
    {"title": "Your weekend", "writing_prompt": "Write a few sentences about what you usually do on weekends.", "min_words": 15, "max_words": 40, "level": 2},
    {"title": "At the airport", "writing_prompt": "Look at the picture. Write ONE sentence using the words 'passengers' and 'wait'.",
     "min_words": 5, "max_words": 20, "level": 2, "image_query": "passengers waiting at airport gate"},

    # --- Level 3 -- A2 -----------------------------------------------------
    {"title": "A place you visited", "writing_prompt": "Write a short paragraph about a city or town you have visited. Include what you saw and what you liked most.", "min_words": 30, "max_words": 80, "level": 3},
    {"title": "Your typical weekday", "writing_prompt": "Describe a typical weekday from morning to evening.", "min_words": 30, "max_words": 80, "level": 3},
    {"title": "At a restaurant", "writing_prompt": "Look at the picture. Write ONE sentence using the words 'waiter' and 'order'.",
     "min_words": 5, "max_words": 20, "level": 3, "image_query": "waiter taking order at restaurant table"},

    # --- Level 4 -- A2 -----------------------------------------------------
    {"title": "A helpful coworker", "writing_prompt": "Describe a time a coworker or classmate helped you with something.", "min_words": 30, "max_words": 80, "level": 4},
    {"title": "Your favorite season", "writing_prompt": "Write a paragraph about your favorite season and why you like it.", "min_words": 30, "max_words": 80, "level": 4},

    # --- Level 5 -- B1 (email response begins) ------------------------------
    {"title": "Email: reschedule a meeting", "writing_prompt": "Write a polite email to a colleague asking to reschedule a meeting from Thursday to Friday afternoon. Explain briefly why you need the change.", "min_words": 50, "max_words": 120, "level": 5},
    {"title": "Email: request time off", "writing_prompt": "Write an email to your manager requesting two days off next month. Include the dates and a brief reason.", "min_words": 50, "max_words": 120, "level": 5},

    # --- Level 6 -- B1 -------------------------------------------------------
    {"title": "Email: thank a client", "writing_prompt": "Write an email thanking a client for their business over the past year and wishing them a happy new year.", "min_words": 50, "max_words": 120, "level": 6},
    {"title": "Email: ask for information", "writing_prompt": "Write an email to a hotel asking about availability and prices for a weekend in July.", "min_words": 50, "max_words": 120, "level": 6},

    # --- Level 7 -- B1 ---------------------------------------------------------
    {"title": "Email: apologize for a delay", "writing_prompt": "Write an email to a customer apologizing for a delayed shipment and explaining what you are doing to fix it.", "min_words": 50, "max_words": 120, "level": 7},
    {"title": "Email: confirm attendance", "writing_prompt": "Write an email confirming that you will attend a company workshop next Tuesday, including one question you have about it.", "min_words": 50, "max_words": 120, "level": 7},
    {"title": "Opinion: remote work preference", "writing_prompt": "Do you prefer working from home or from an office? Write a short paragraph explaining your preference.", "min_words": 50, "max_words": 120, "level": 7},

    # --- Level 8 -- B2 -----------------------------------------------------------
    {"title": "Email: negotiate a deadline", "writing_prompt": "Write an email to your manager explaining why you need more time to complete a project, and propose a new deadline.", "min_words": 80, "max_words": 160, "level": 8},
    {"title": "Opinion: daily team meetings", "writing_prompt": "Do you think daily team meetings improve or hurt productivity? Write a paragraph with at least one supporting reason.", "min_words": 80, "max_words": 160, "level": 8},

    # --- Level 9 -- B2 -------------------------------------------------------------
    {"title": "Email: respond to a complaint", "writing_prompt": "A customer has emailed complaining about a late delivery. Write a professional reply addressing their concern and offering a solution.", "min_words": 80, "max_words": 160, "level": 9},
    {"title": "Opinion: remote work productivity", "writing_prompt": "Do you think remote work improves productivity? Write a short opinion paragraph with at least one reason supporting your view.", "min_words": 80, "max_words": 160, "level": 9},

    # --- Level 10 -- C1 (opinion essay begins) --------------------------------------
    {"title": "Essay: open-plan offices", "writing_prompt": "Some companies believe open-plan offices improve collaboration, while others believe they reduce focus. Write an essay giving your opinion, with reasons and examples.", "min_words": 120, "max_words": 220, "level": 10},
    {"title": "Essay: work-life balance", "writing_prompt": "Is it the employer's or the employee's responsibility to maintain a healthy work-life balance? Give your opinion with supporting reasons.", "min_words": 120, "max_words": 220, "level": 10},

    # --- Level 11 -- C1 -----------------------------------------------------------------
    {"title": "Essay: automation and jobs", "writing_prompt": "Some people believe automation will create more jobs than it eliminates. Do you agree or disagree? Support your opinion with reasons and examples.", "min_words": 120, "max_words": 220, "level": 11},
    {"title": "Essay: business travel vs. video calls", "writing_prompt": "Has video conferencing made business travel unnecessary? Give your opinion, supported by specific reasons.", "min_words": 120, "max_words": 220, "level": 11},

    # --- Level 12 -- C1 -----------------------------------------------------------------
    {"title": "Essay: performance-based pay", "writing_prompt": "Should employee pay be based mainly on individual performance rather than seniority? Discuss both sides and give your opinion.", "min_words": 120, "max_words": 220, "level": 12},
    {"title": "Essay: four-day work week", "writing_prompt": "Would a four-day work week benefit most companies? Support your opinion with clear reasons and examples.", "min_words": 120, "max_words": 220, "level": 12},

    # --- Level 13 -- C2 (advanced opinion essay) -----------------------------------------
    {"title": "Essay: AI in hiring", "writing_prompt": "Companies increasingly use AI tools to screen job applicants. Do the benefits outweigh the risks? Write a well-supported essay.", "min_words": 180, "max_words": 300, "level": 13},
    {"title": "Essay: globalization and small business", "writing_prompt": "Has globalization been, on balance, positive or negative for small businesses? Support your argument with specific reasoning.", "min_words": 180, "max_words": 300, "level": 13},

    # --- Level 14 -- C2 -----------------------------------------------------------------
    {"title": "Essay: corporate sustainability", "writing_prompt": "Should companies prioritize environmental sustainability even when it reduces short-term profit? Argue your position with well-developed reasoning.", "min_words": 180, "max_words": 300, "level": 14},
    {"title": "Essay: mandatory retirement age", "writing_prompt": "Should companies be allowed to set a mandatory retirement age? Present a clear position supported by reasoning.", "min_words": 180, "max_words": 300, "level": 14},

    # --- Level 15 -- C2 -----------------------------------------------------------------
    {"title": "Essay: what makes a leader", "writing_prompt": "What quality matters most in an effective business leader: experience, vision, or empathy? Argue for one, addressing the strongest counterargument.", "min_words": 180, "max_words": 300, "level": 15},
    {"title": "Essay: measuring company success", "writing_prompt": "Should company success be measured primarily by profit, or should factors like employee wellbeing and social impact weigh equally? Defend your position.", "min_words": 180, "max_words": 300, "level": 15},
]


class Command(BaseCommand):
    help = "Replace the Writing SkillLesson catalog with the full 15-level TOEIC set."

    @transaction.atomic
    def handle(self, *args, **options):
        writing_skill = Skill.objects.filter(slug="writing").first()
        if not writing_skill:
            self.stderr.write(self.style.ERROR("Writing skill not found — run seed_skills first."))
            return

        deleted, _ = SkillLesson.objects.filter(skill=writing_skill).delete()
        self.stdout.write(f"Deleted {deleted} existing row(s) (SkillLesson + cascaded completions).")

        created = 0
        images_found = 0
        used_slugs = set()
        for order, row in enumerate(WRITING_LESSON_SEED, start=1):
            row = dict(row)
            image_query = row.pop("image_query", None)

            base_slug = slugify(row["title"])[:80]
            slug = base_slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug[:76]}-{suffix}"
                suffix += 1
            used_slugs.add(slug)

            image_url = ""
            image_credit = ""
            if image_query:
                photo = get_stock_image(image_query)
                if photo:
                    image_url = photo["url"]
                    image_credit = photo["credit"]
                    images_found += 1

            SkillLesson.objects.create(
                skill=writing_skill,
                slug=slug,
                sort_order=order,
                is_published=True,
                image_url=image_url,
                image_credit=image_credit,
                **row,
            )
            created += 1

        total = SkillLesson.objects.filter(skill=writing_skill).count()
        self.stdout.write(self.style.SUCCESS(
            f"Writing seed complete: {total} lesson(s), {created} created, {images_found} photo(s) resolved."
        ))
