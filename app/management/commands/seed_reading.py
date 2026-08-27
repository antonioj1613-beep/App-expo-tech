"""
Seed the full 15-level TOEIC reading catalog into SkillLesson.

Replaces the entire existing Reading catalog on every run (--replace
semantics, always on), mirroring seed_vocabulary_lessons.py: deletes all
SkillLesson rows for skill=reading first, then recreates the full 53-item
set below via a per-item create() loop (keeps the post_save signal that
syncs Skill.total_lessons — see signals.sync_skill_lesson_count).

Three item types, all inside the existing schema:
- P5-style grammar/vocab-in-context: passage = one sentence with a blank.
- P6-style text completion: passage = a short memo/email/notice with a blank.
- P7-style reading comprehension: full passage + comprehension question.
Multi-question sets (P7's real multi-part format) share identical passage
text across 2-3 rows with different questions, starting at level 7.

Level -> CEFR band matches gamification.LESSON_LEVEL_TO_CEFR_BAND exactly:
1-2 A1, 3-4 A2, 5-7 B1, 8-9 B2, 10-12 C1, 13-15 C2.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from app.models import Skill, SkillLesson

COMPLETE_SENTENCE = "Choose the word that best completes the sentence."
COMPLETE_TEXT = "Choose the word that best completes the text."

READING_LESSON_SEED = [
    # --- Level 1 -- A1 ---------------------------------------------------
    {"title": "Grammar: sister lives in Madrid", "passage": "My sister _____ in Madrid.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["live", "lives", "living", "lived"], "correct_index": 1, "level": 1},
    {"title": "Grammar: breakfast at seven", "passage": "I usually eat breakfast _____ 7 a.m.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["in", "on", "at", "for"], "correct_index": 2, "level": 1},
    {"title": "Gym hours notice", "passage": "City Gym — Notice\n\nThe gym opens at 6 a.m. and closes at 10 p.m. every day. On Sundays, it closes at 8 p.m.",
     "question_prompt": "What time does the gym close on Sundays?", "options": ["6 a.m.", "8 p.m.", "10 p.m.", "It is closed."], "correct_index": 1, "level": 1},

    # --- Level 2 -- A1 ---------------------------------------------------
    {"title": "Grammar: two chairs in office", "passage": "There _____ two chairs in the office.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["is", "am", "are", "be"], "correct_index": 2, "level": 2},
    {"title": "Grammar: works Monday to Friday", "passage": "She works _____ Monday to Friday.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["from", "at", "in", "on"], "correct_index": 0, "level": 2},
    {"title": "Parking notice", "passage": "Parking Notice\n\nVisitors may park in Lot B only. Lot A is reserved for staff. Parking is free for the first two hours.",
     "question_prompt": "Where can visitors park?", "options": ["Lot A", "Lot B", "Both lots", "Nowhere"], "correct_index": 1, "level": 2},

    # --- Level 3 -- A2 ---------------------------------------------------
    {"title": "Grammar: responsible for managing", "passage": "He is responsible _____ managing the team's schedule.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["of", "for", "with", "at"], "correct_index": 1, "level": 3},
    {"title": "Office memo — expense reports", "passage": "Memo\n\nAll staff must submit expense reports by the 5th of each _____. Late submissions will not be processed.",
     "question_prompt": COMPLETE_TEXT, "options": ["hour", "week", "month", "minute"], "correct_index": 2, "level": 3},
    {"title": "Coffee shop closing early", "passage": "Notice: Green Bean Café\n\nDue to staff training, the café will close at 2 p.m. today instead of the usual 6 p.m. We apologize for any inconvenience and will reopen tomorrow at the normal time.",
     "question_prompt": "Why is the café closing early today?", "options": ["A holiday", "Staff training", "A power outage", "Low customer numbers"], "correct_index": 1, "level": 3},

    # --- Level 4 -- A2 ---------------------------------------------------
    {"title": "Grammar: arrive on time", "passage": "Please arrive _____ time for the interview.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["on", "in", "at", "by"], "correct_index": 0, "level": 4},
    {"title": "Delivery update — package shipped", "passage": "Delivery Update\n\nYour package has been _____ and should arrive within two business days. You will receive a text message when it is out for delivery.",
     "question_prompt": COMPLETE_TEXT, "options": ["canceled", "shipped", "lost", "returned"], "correct_index": 1, "level": 4},
    {"title": "Library renovation notice", "passage": "City Library Notice\n\nThe second floor will be closed for renovation from June 1 to June 15. The first floor and study rooms remain open as usual during this time.",
     "question_prompt": "What can visitors still use during the renovation?", "options": ["The second floor", "Nothing", "The first floor and study rooms", "Only the study rooms"], "correct_index": 2, "level": 4},

    # --- Level 5 -- B1 ---------------------------------------------------
    {"title": "Grammar: meeting postponed", "passage": "The meeting has been _____ to next Wednesday.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["postponed", "posted", "posting", "post"], "correct_index": 0, "level": 5},
    {"title": "Team announcement — office relocation", "passage": "Team Announcement\n\nStarting Monday, the marketing team will _____ from the third floor to the fifth floor. Please update your contact list accordingly.",
     "question_prompt": COMPLETE_TEXT, "options": ["relocate", "resign", "return", "repeat"], "correct_index": 0, "level": 5},
    {"title": "New printer instructions", "passage": "Office Notice: New Printer\n\nThe new printer on the second floor supports double-sided printing and scanning to email. For color printing, use the printer on the fourth floor instead, as this one prints in black and white only.",
     "question_prompt": "What can the second-floor printer NOT do?", "options": ["Print double-sided", "Scan to email", "Print in color", "Print in black and white"], "correct_index": 2, "level": 5},

    # --- Level 6 -- B1 ---------------------------------------------------
    {"title": "Client email — inquiry about services", "passage": "Dear Mr. Alvarez,\n\nThank you for your _____ about our services. Attached is the pricing information you requested. Please let me know if you have any questions.\n\nBest regards,\nLena",
     "question_prompt": COMPLETE_TEXT, "options": ["inquiry", "invoice", "complaint", "apology"], "correct_index": 0, "level": 6},
    {"title": "Software update notice", "passage": "System Notice\n\nThe accounting software will be updated this Friday at 6 p.m. The system will be unavailable for about one hour. Please save your work and log off before 5:45 p.m.",
     "question_prompt": "What should employees do before 5:45 p.m. on Friday?", "options": ["Update the software themselves", "Save their work and log off", "Come to the office early", "Call IT support"], "correct_index": 1, "level": 6},
    {"title": "Conference room booking", "passage": "Conference Room Policy\n\nRooms can be booked up to two weeks in advance through the booking app. Bookings longer than two hours require manager approval. Unused bookings are automatically canceled after 15 minutes.",
     "question_prompt": "What happens if a booked room is not used within 15 minutes?", "options": ["The booking is automatically canceled", "The manager is notified", "The room is locked", "A fee is charged"], "correct_index": 0, "level": 6},

    # --- Level 7 -- B1 (first multi-question set) ------------------------
    {"title": "Staff newsletter — new cafeteria", "passage": "Staff Newsletter\n\nWe are pleased to _____ that the new cafeteria will open next month, offering healthier meal options for all employees.",
     "question_prompt": COMPLETE_TEXT, "options": ["announce", "cancel", "deny", "postpone"], "correct_index": 0, "level": 7},
    {"title": "Travel policy update (1/2)", "passage": "Travel Policy Update\n\nEffective next quarter, all business travel over $500 must be approved by a department head at least one week in advance. Employees should submit requests through the new travel portal. Reimbursement requests must include original receipts and be filed within 30 days of the trip.",
     "question_prompt": "How far in advance must travel over $500 be approved?", "options": ["One day", "One week", "One month", "No advance notice needed"], "correct_index": 1, "level": 7},
    {"title": "Travel policy update (2/2)", "passage": "Travel Policy Update\n\nEffective next quarter, all business travel over $500 must be approved by a department head at least one week in advance. Employees should submit requests through the new travel portal. Reimbursement requests must include original receipts and be filed within 30 days of the trip.",
     "question_prompt": "What must be included with a reimbursement request?", "options": ["A manager's signature only", "Original receipts", "A travel itinerary", "Passport copy"], "correct_index": 1, "level": 7},

    # --- Level 8 -- B2 -----------------------------------------------------
    {"title": "Grammar: insufficient evidence", "passage": "The proposal was rejected due to _____ evidence.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["insufficient", "sufficient", "efficient", "proficient"], "correct_index": 0, "level": 8},
    {"title": "Vendor letter — contract renewal", "passage": "Dear Supplier,\n\nWe would like to _____ our current contract for an additional twelve months under the same terms, unless you propose otherwise.\n\nRegards,\nProcurement Team",
     "question_prompt": COMPLETE_TEXT, "options": ["terminate", "renew", "ignore", "lose"], "correct_index": 1, "level": 8},
    {"title": "Customer service report (1/2)", "passage": "Customer Service Quarterly Report\n\nResponse times improved by 18% this quarter after the team adopted a new ticketing system. However, customer satisfaction scores remained flat, suggesting that speed alone does not guarantee a better experience. Management plans to introduce quality-focused training next quarter to address this gap.",
     "question_prompt": "What improved this quarter, according to the report?", "options": ["Customer satisfaction scores", "Response times", "Staff numbers", "Ticket volume"], "correct_index": 1, "level": 8},
    {"title": "Customer service report (2/2)", "passage": "Customer Service Quarterly Report\n\nResponse times improved by 18% this quarter after the team adopted a new ticketing system. However, customer satisfaction scores remained flat, suggesting that speed alone does not guarantee a better experience. Management plans to introduce quality-focused training next quarter to address this gap.",
     "question_prompt": "What does the report suggest management will do next quarter?", "options": ["Hire more staff", "Reduce ticket volume", "Introduce quality-focused training", "Replace the ticketing system"], "correct_index": 2, "level": 8},

    # --- Level 9 -- B2 -----------------------------------------------------
    {"title": "Grammar: sales figures risen", "passage": "Sales figures _____ significantly since the campaign launched.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["has risen", "have risen", "rising", "rise"], "correct_index": 1, "level": 9},
    {"title": "Internal memo — reduce travel costs", "passage": "Internal Memo\n\nTo reduce costs, all departments are asked to _____ non-essential travel until further notice. Video conferencing should be used whenever possible.",
     "question_prompt": COMPLETE_TEXT, "options": ["increase", "limit", "encourage", "reward"], "correct_index": 1, "level": 9},
    {"title": "Product recall notice (1/2)", "passage": "Product Recall Notice\n\nDueTech Inc. is recalling its model X200 charger after reports of overheating during use. Customers who purchased the charger between January and March should stop using it immediately and contact customer support for a free replacement. No injuries have been reported.",
     "question_prompt": "Why is the charger being recalled?", "options": ["It stopped working", "It overheated", "It was too expensive", "It was discontinued"], "correct_index": 1, "level": 9},
    {"title": "Product recall notice (2/2)", "passage": "Product Recall Notice\n\nDueTech Inc. is recalling its model X200 charger after reports of overheating during use. Customers who purchased the charger between January and March should stop using it immediately and contact customer support for a free replacement. No injuries have been reported.",
     "question_prompt": "What should affected customers do?", "options": ["Return it to any store", "Continue using it carefully", "Contact customer support for a replacement", "Wait for a refund automatically"], "correct_index": 2, "level": 9},

    # --- Level 10 -- C1 (first 3-question set) ------------------------------
    {"title": "Board memo — cautious expansion", "passage": "Board Memo\n\nGiven current market conditions, the board recommends a cautious approach to expansion, prioritizing _____ over rapid growth this fiscal year.",
     "question_prompt": COMPLETE_TEXT, "options": ["stability", "volatility", "bankruptcy", "exposure"], "correct_index": 0, "level": 10},
    {"title": "Merger announcement (1/2)", "passage": "Merger Announcement\n\nNova Systems and BrightPath Technologies announced today that they will merge into a single entity by the end of the year. The combined company, to be named NovaBright, will retain employees from both firms and aims to expand its presence in the renewable energy sector. Shareholders from both companies must approve the deal at a vote scheduled for next month.",
     "question_prompt": "What is the purpose of next month's vote?", "options": ["To elect a new CEO", "To approve the merger", "To set new prices", "To cancel the merger"], "correct_index": 1, "level": 10},
    {"title": "Merger announcement (2/2)", "passage": "Merger Announcement\n\nNova Systems and BrightPath Technologies announced today that they will merge into a single entity by the end of the year. The combined company, to be named NovaBright, will retain employees from both firms and aims to expand its presence in the renewable energy sector. Shareholders from both companies must approve the deal at a vote scheduled for next month.",
     "question_prompt": "Which sector does the merged company plan to expand into?", "options": ["Renewable energy", "Retail", "Banking", "Agriculture"], "correct_index": 0, "level": 10},
    {"title": "Compliance training reminder", "passage": "Compliance Reminder\n\nAll employees must complete the annual compliance training module by the end of the month. Managers whose teams fall below 90% completion will be required to submit a remediation plan to Human Resources.",
     "question_prompt": "What happens if a team's completion rate is below 90%?", "options": ["The team is dissolved", "The manager submits a remediation plan", "Employees are fined", "Training is canceled"], "correct_index": 1, "level": 10},

    # --- Level 11 -- C1 ------------------------------------------------------
    {"title": "Grammar: decision provoked backlash", "passage": "The committee's decision _____ significant backlash from employees.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["provoked", "prevented", "proved", "protected"], "correct_index": 0, "level": 11},
    {"title": "Investor update — performance rebound", "passage": "Investor Update\n\nDespite a challenging quarter, we remain confident in our long-term strategy and expect performance to _____ as new contracts take effect.",
     "question_prompt": COMPLETE_TEXT, "options": ["deteriorate", "stagnate", "rebound", "vanish"], "correct_index": 2, "level": 11},
    {"title": "Workplace survey results (1/2)", "passage": "Workplace Survey Results\n\nA recent internal survey found that 68% of employees favor a hybrid work model over fully remote or fully in-office arrangements. The most commonly cited reason was a desire for flexibility combined with in-person collaboration. Management is reviewing the results to inform an updated workplace policy expected next quarter.",
     "question_prompt": "What did most employees say they prefer?", "options": ["Fully remote work", "Fully in-office work", "A hybrid model", "No preference"], "correct_index": 2, "level": 11},
    {"title": "Workplace survey results (2/2)", "passage": "Workplace Survey Results\n\nA recent internal survey found that 68% of employees favor a hybrid work model over fully remote or fully in-office arrangements. The most commonly cited reason was a desire for flexibility combined with in-person collaboration. Management is reviewing the results to inform an updated workplace policy expected next quarter.",
     "question_prompt": "When is the updated policy expected?", "options": ["Immediately", "Next quarter", "Next year", "It was already published"], "correct_index": 1, "level": 11},

    # --- Level 12 -- C1 (first 3-question set) --------------------------------
    {"title": "Legal notice — dispute terms", "passage": "Legal Notice\n\nAny party wishing to dispute the terms outlined in this agreement must submit a formal objection in writing within thirty days, after which the terms shall be considered _____ accepted by all parties.",
     "question_prompt": COMPLETE_TEXT, "options": ["tentatively", "irrevocably", "rarely", "accidentally"], "correct_index": 1, "level": 12},
    {"title": "Quarterly earnings summary (1/3)", "passage": "Quarterly Earnings Summary\n\nThe company reported revenue of $42 million for the quarter, a 7% increase year-over-year, driven primarily by strong performance in the international division. Operating costs also rose, however, due to higher shipping expenses linked to global supply chain disruptions. Management expects these cost pressures to ease by the second half of the year, and has reaffirmed full-year revenue guidance despite the near-term headwinds.",
     "question_prompt": "What drove the revenue increase?", "options": ["Lower shipping costs", "Strong performance in the international division", "A reduction in operating costs", "A one-time asset sale"], "correct_index": 1, "level": 12},
    {"title": "Quarterly earnings summary (2/3)", "passage": "Quarterly Earnings Summary\n\nThe company reported revenue of $42 million for the quarter, a 7% increase year-over-year, driven primarily by strong performance in the international division. Operating costs also rose, however, due to higher shipping expenses linked to global supply chain disruptions. Management expects these cost pressures to ease by the second half of the year, and has reaffirmed full-year revenue guidance despite the near-term headwinds.",
     "question_prompt": "Why did operating costs rise?", "options": ["New hires", "Higher shipping expenses", "A tax increase", "Currency exchange losses"], "correct_index": 1, "level": 12},
    {"title": "Quarterly earnings summary (3/3)", "passage": "Quarterly Earnings Summary\n\nThe company reported revenue of $42 million for the quarter, a 7% increase year-over-year, driven primarily by strong performance in the international division. Operating costs also rose, however, due to higher shipping expenses linked to global supply chain disruptions. Management expects these cost pressures to ease by the second half of the year, and has reaffirmed full-year revenue guidance despite the near-term headwinds.",
     "question_prompt": "What does management expect for the second half of the year?", "options": ["Cost pressures will ease", "Revenue guidance will be lowered", "The international division will close", "Shipping costs will double"], "correct_index": 0, "level": 12},

    # --- Level 13 -- C2 (first 3-question set) ---------------------------------
    {"title": "Arbitration clause — dispute resolution", "passage": "Arbitration Clause\n\nAny dispute arising under this agreement that cannot be resolved through negotiation shall be _____ to binding arbitration in accordance with the rules of the International Chamber of Commerce.",
     "question_prompt": COMPLETE_TEXT, "options": ["submitted", "forgiven", "postponed", "publicized"], "correct_index": 0, "level": 13},
    {"title": "Industry analysis: automation (1/3)", "passage": "Industry Analysis: The Shift Toward Automation\n\nAcross manufacturing sectors, firms are increasingly investing in automation not merely to cut labor costs, but to mitigate the volatility associated with an aging and shrinking skilled workforce. Critics argue this trend risks displacing workers faster than new roles can be created, while proponents counter that automation historically has generated more jobs than it eliminates, provided retraining programs keep pace with technological change. The debate remains unresolved, though most analysts agree that the pace of adoption will only accelerate over the next decade.",
     "question_prompt": "Why are firms increasingly investing in automation, according to the passage?", "options": ["Purely to cut labor costs", "To mitigate workforce volatility", "Government regulation requires it", "To eliminate all human jobs"], "correct_index": 1, "level": 13},
    {"title": "Industry analysis: automation (2/3)", "passage": "Industry Analysis: The Shift Toward Automation\n\nAcross manufacturing sectors, firms are increasingly investing in automation not merely to cut labor costs, but to mitigate the volatility associated with an aging and shrinking skilled workforce. Critics argue this trend risks displacing workers faster than new roles can be created, while proponents counter that automation historically has generated more jobs than it eliminates, provided retraining programs keep pace with technological change. The debate remains unresolved, though most analysts agree that the pace of adoption will only accelerate over the next decade.",
     "question_prompt": "What do critics of automation argue?", "options": ["It creates too many new jobs", "It risks displacing workers faster than new roles are created", "It has no effect on employment", "It reduces production quality"], "correct_index": 1, "level": 13},
    {"title": "Industry analysis: automation (3/3)", "passage": "Industry Analysis: The Shift Toward Automation\n\nAcross manufacturing sectors, firms are increasingly investing in automation not merely to cut labor costs, but to mitigate the volatility associated with an aging and shrinking skilled workforce. Critics argue this trend risks displacing workers faster than new roles can be created, while proponents counter that automation historically has generated more jobs than it eliminates, provided retraining programs keep pace with technological change. The debate remains unresolved, though most analysts agree that the pace of adoption will only accelerate over the next decade.",
     "question_prompt": "What do most analysts agree on?", "options": ["Automation adoption will slow down", "Automation adoption will accelerate", "Automation will be banned", "Retraining programs are unnecessary"], "correct_index": 1, "level": 13},

    # --- Level 14 -- C2 (first 3-question set) ----------------------------------
    {"title": "Grammar: findings suggestive", "passage": "The findings, while _____ , do not conclusively support the original hypothesis.",
     "question_prompt": COMPLETE_SENTENCE, "options": ["suggestive", "suggested", "suggestion", "suggestively"], "correct_index": 0, "level": 14},
    {"title": "Corporate governance report (1/3)", "passage": "Corporate Governance Report\n\nShareholder activism has intensified in recent years, with institutional investors increasingly using their voting power to push for changes in executive compensation, board composition, and environmental disclosure. While some executives view this scrutiny as an unwelcome distraction from day-to-day operations, a growing body of research suggests that companies subject to sustained activist pressure tend to outperform their peers over a five-year horizon, likely due to improved governance discipline rather than the specific demands themselves.",
     "question_prompt": "What are institutional investors increasingly pushing for?", "options": ["Lower shareholder involvement", "Changes in compensation, board composition, and disclosure", "Immediate liquidation", "Reduced regulatory oversight"], "correct_index": 1, "level": 14},
    {"title": "Corporate governance report (2/3)", "passage": "Corporate Governance Report\n\nShareholder activism has intensified in recent years, with institutional investors increasingly using their voting power to push for changes in executive compensation, board composition, and environmental disclosure. While some executives view this scrutiny as an unwelcome distraction from day-to-day operations, a growing body of research suggests that companies subject to sustained activist pressure tend to outperform their peers over a five-year horizon, likely due to improved governance discipline rather than the specific demands themselves.",
     "question_prompt": "How do some executives view shareholder activism?", "options": ["As a welcome opportunity", "As an unwelcome distraction", "As irrelevant", "As a legal requirement"], "correct_index": 1, "level": 14},
    {"title": "Corporate governance report (3/3)", "passage": "Corporate Governance Report\n\nShareholder activism has intensified in recent years, with institutional investors increasingly using their voting power to push for changes in executive compensation, board composition, and environmental disclosure. While some executives view this scrutiny as an unwelcome distraction from day-to-day operations, a growing body of research suggests that companies subject to sustained activist pressure tend to outperform their peers over a five-year horizon, likely due to improved governance discipline rather than the specific demands themselves.",
     "question_prompt": "What does research suggest about companies under activist pressure?", "options": ["They tend to underperform", "They tend to outperform peers over five years", "They usually go bankrupt", "They see no measurable effect"], "correct_index": 1, "level": 14},

    # --- Level 15 -- C2 (combined two-document passage) -----------------------------
    {"title": "Executive memo — restructuring deferred", "passage": "Executive Memo\n\nIn light of the findings outlined above, the executive committee has resolved to _____ the proposed restructuring pending a more comprehensive risk assessment.",
     "question_prompt": COMPLETE_TEXT, "options": ["expedite", "defer", "publicize", "finalize"], "correct_index": 1, "level": 15},
    {"title": "Email + policy excerpt (1/3)", "passage": "From: Priya Nair, Head of Compliance\nTo: All Department Heads\nSubject: Updated Data Retention Policy\n\nPlease review the attached policy excerpt below and ensure your teams are briefed by month's end.\n\n---\nData Retention Policy (excerpt)\n\nAll customer records must be retained for a minimum of seven years from the date of last transaction, after which they must be securely deleted unless subject to an active legal hold. Departments found non-compliant during the annual audit will be required to submit a corrective action plan within fourteen days.",
     "question_prompt": "What is the minimum retention period for customer records?", "options": ["One year", "Three years", "Seven years", "Indefinitely"], "correct_index": 2, "level": 15},
    {"title": "Email + policy excerpt (2/3)", "passage": "From: Priya Nair, Head of Compliance\nTo: All Department Heads\nSubject: Updated Data Retention Policy\n\nPlease review the attached policy excerpt below and ensure your teams are briefed by month's end.\n\n---\nData Retention Policy (excerpt)\n\nAll customer records must be retained for a minimum of seven years from the date of last transaction, after which they must be securely deleted unless subject to an active legal hold. Departments found non-compliant during the annual audit will be required to submit a corrective action plan within fourteen days.",
     "question_prompt": "What must department heads do by month's end?", "options": ["Delete all records", "Brief their teams on the policy", "Submit a corrective action plan", "Conduct the annual audit"], "correct_index": 1, "level": 15},
    {"title": "Email + policy excerpt (3/3)", "passage": "From: Priya Nair, Head of Compliance\nTo: All Department Heads\nSubject: Updated Data Retention Policy\n\nPlease review the attached policy excerpt below and ensure your teams are briefed by month's end.\n\n---\nData Retention Policy (excerpt)\n\nAll customer records must be retained for a minimum of seven years from the date of last transaction, after which they must be securely deleted unless subject to an active legal hold. Departments found non-compliant during the annual audit will be required to submit a corrective action plan within fourteen days.",
     "question_prompt": "What happens if a department is found non-compliant during the audit?", "options": ["It is shut down", "It must submit a corrective action plan within 14 days", "Nothing, it is only a warning", "The department head is replaced"], "correct_index": 1, "level": 15},
]


class Command(BaseCommand):
    help = "Replace the Reading SkillLesson catalog with the full 15-level TOEIC set."

    @transaction.atomic
    def handle(self, *args, **options):
        reading_skill = Skill.objects.filter(slug="reading").first()
        if not reading_skill:
            self.stderr.write(self.style.ERROR("Reading skill not found — run seed_skills first."))
            return

        deleted, _ = SkillLesson.objects.filter(skill=reading_skill).delete()
        self.stdout.write(f"Deleted {deleted} existing row(s) (SkillLesson + cascaded completions).")

        created = 0
        used_slugs = set()
        for order, row in enumerate(READING_LESSON_SEED, start=1):
            base_slug = slugify(row["title"])[:80]
            slug = base_slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug[:76]}-{suffix}"
                suffix += 1
            used_slugs.add(slug)

            SkillLesson.objects.create(
                skill=reading_skill,
                slug=slug,
                sort_order=order,
                is_published=True,
                **row,
            )
            created += 1

        total = SkillLesson.objects.filter(skill=reading_skill).count()
        self.stdout.write(self.style.SUCCESS(f"Reading seed complete: {total} lesson(s), {created} created."))
