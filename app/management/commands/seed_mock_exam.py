"""
Seed one original TOEIC-style mock exam into MockExam/MockExamQuestion.

Replaces this exam's question set on every run (delete-then-recreate for
this slug only, not every MockExam — unlike seed_listening.py this command
is additive across multiple exams over time, so it must not touch other
exams' rows).

Deliberately a smaller, honest scale (20 questions / 25 minutes) rather than
padding out to the real TOEIC's 200-question / 120-minute length with filler
-- every question here is original content, written for this app, never
copied or adapted from real ETS materials (same rule as SkillLesson.image_url
and speaking_tutor.py's TOEIC-prep framing).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import MockExam, MockExamQuestion

EXAM_SLUG = "toeic-practice-1"

LISTENING_QUESTIONS = [
    {
        "passage": "Where should I put these boxes?",
        "question_prompt": "Choose the best response to what you hear.",
        "options": ["Next to the shelf, please.", "I bought them yesterday.", "Yes, I like it.", "At two o'clock."],
        "correct_index": 0,
        "explanation": "A \"where\" question needs a location in the answer — \"next to the shelf\" is the only option that gives one.",
    },
    {
        "passage": "Could you send me the report before lunch?",
        "question_prompt": "Choose the best response to what you hear.",
        "options": ["It's raining outside.", "Sure, I'll have it ready by noon.", "I don't have any siblings.", "The meeting was cancelled."],
        "correct_index": 1,
        "explanation": "A request (\"Could you...\") is answered with an agreement/commitment — only option B responds to the request itself.",
    },
    {
        "passage": "Manager: Have you finished the inventory count?\nEmployee: Almost — I have about twenty items left to check.\nManager: Take your time, just get it done before we close.\nEmployee: Will do, thanks.",
        "question_prompt": "What is the employee doing?",
        "options": ["Closing the store", "Counting inventory", "Hiring new staff", "Writing a report"],
        "correct_index": 1,
        "explanation": "The employee explicitly says twenty items are left \"to check\" as part of an inventory count the manager asked about.",
    },
    {
        "passage": "Attention shoppers, our electronics department is offering twenty percent off all headphones for the next hour only. Visit aisle twelve to see the full selection.",
        "question_prompt": "What is being announced?",
        "options": ["A store closing", "A temporary discount", "A new store location", "A product recall"],
        "correct_index": 1,
        "explanation": "\"Twenty percent off... for the next hour only\" describes a limited-time discount, not a closing, new location, or recall.",
    },
    {
        "passage": "Who's presenting at the conference next week?",
        "question_prompt": "Choose the best response to what you hear.",
        "options": ["It starts at nine.", "In the main hall.", "Sarah from marketing is.", "It was very informative."],
        "correct_index": 2,
        "explanation": "\"Who\" asks for a person — only \"Sarah from marketing is\" names one.",
    },
    {
        "passage": "Receptionist: Dr. Lin's office, how can I help you?\nCaller: I'd like to reschedule my appointment from Thursday to Friday.\nReceptionist: Let me check... Friday at 3 PM is open.\nCaller: That works, thank you.",
        "question_prompt": "Why is the caller contacting the office?",
        "options": ["To cancel an appointment", "To ask about billing", "To reschedule an appointment", "To request a prescription"],
        "correct_index": 2,
        "explanation": "The caller directly says \"I'd like to reschedule my appointment\" — not cancel, ask about billing, or request anything else.",
    },
    {
        "passage": "The 4:15 train to Riverside has been delayed by twenty minutes due to signal maintenance. We apologize for the inconvenience.",
        "question_prompt": "Why is there a delay?",
        "options": ["Bad weather", "Signal maintenance", "A staff shortage", "A ticket problem"],
        "correct_index": 1,
        "explanation": "The announcement states the delay is \"due to signal maintenance\" directly.",
    },
    {
        "passage": "How long have you worked at this company?",
        "question_prompt": "Choose the best response to what you hear.",
        "options": ["It's on the third floor.", "About five years now.", "No, I haven't seen it.", "He's my supervisor."],
        "correct_index": 1,
        "explanation": "\"How long\" asks for a duration — only \"about five years now\" answers with one.",
    },
    {
        "passage": "Colleague A: Did you hear the printer on the second floor is broken again?\nColleague B: Yeah, I already called IT. They said someone will look at it this afternoon.\nColleague A: Good, I need to print some contracts today.",
        "question_prompt": "What problem is being discussed?",
        "options": ["A broken printer", "A late delivery", "A canceled meeting", "A software update"],
        "correct_index": 0,
        "explanation": "Both speakers are talking about the printer on the second floor being broken and IT coming to fix it.",
    },
    {
        "passage": "Welcome aboard flight 220 to Chicago. Please make sure your seat belt is fastened and your tray table is stowed for takeoff.",
        "question_prompt": "Where is this announcement most likely being made?",
        "options": ["On an airplane", "In a train station", "In a hotel lobby", "At a bus stop"],
        "correct_index": 0,
        "explanation": "\"Flight,\" \"seat belt,\" and \"tray table\" for \"takeoff\" are all specific to an airplane cabin announcement.",
    },
]

READING_QUESTIONS = [
    {
        "passage": "The marketing team ___ the new campaign results at tomorrow's meeting.",
        "question_prompt": "Choose the word that best completes the sentence.",
        "options": ["present", "presents", "will present", "presenting"],
        "correct_index": 2,
        "explanation": "\"Tomorrow's meeting\" signals a future event, so the future tense \"will present\" is correct.",
    },
    {
        "passage": "Employees are required to submit their expense reports ___ the last day of each month.",
        "question_prompt": "Choose the word that best completes the sentence.",
        "options": ["by", "since", "during", "between"],
        "correct_index": 0,
        "explanation": "\"By\" expresses a deadline (\"no later than\"), matching \"required to submit... the last day of each month.\"",
    },
    {
        "passage": "Despite ___ the deadline, the project team delivered a high-quality product.",
        "question_prompt": "Choose the word that best completes the sentence.",
        "options": ["missed", "missing", "to miss", "misses"],
        "correct_index": 1,
        "explanation": "\"Despite\" is followed by a gerund (-ing form) when introducing a clause, so \"missing\" is correct.",
    },
    {
        "passage": "Notice: The office will be closed on Monday for building maintenance. All staff should work remotely that day. Regular hours resume Tuesday.",
        "question_prompt": "What should employees do on Monday?",
        "options": ["Come to the office early", "Work from home", "Take the day off", "Attend a maintenance training"],
        "correct_index": 1,
        "explanation": "The notice says \"All staff should work remotely\" on Monday, i.e. work from home.",
    },
    {
        "passage": "Dear Ms. Patel,\nThank you for your application for the Senior Analyst position. We were impressed by your background and would like to invite you for an interview next Wednesday at 10 AM. Please confirm your availability.\nBest regards,\nHR Department",
        "question_prompt": "What is the purpose of this email?",
        "options": ["To reject an application", "To request payment", "To schedule an interview", "To announce a promotion"],
        "correct_index": 2,
        "explanation": "The email invites Ms. Patel \"for an interview next Wednesday\" and asks her to confirm — its purpose is scheduling an interview.",
    },
    {
        "passage": "The new software update ___ several bugs that users reported last month.",
        "question_prompt": "Choose the word that best completes the sentence.",
        "options": ["fix", "fixes", "fixing", "to fix"],
        "correct_index": 1,
        "explanation": "The subject \"The new software update\" is singular/third-person, so the verb takes -s: \"fixes.\"",
    },
    {
        "passage": "All visitors must sign in at the front desk ___ entering the laboratory area.",
        "question_prompt": "Choose the word that best completes the sentence.",
        "options": ["before", "although", "because", "unless"],
        "correct_index": 0,
        "explanation": "Signing in happens prior to entering the lab, so the time-sequence word \"before\" fits, not the contrast/reason/condition words.",
    },
    {
        "passage": "Warehouse Update: Due to high demand, delivery times for all furniture orders are currently 7-10 business days instead of the usual 3-5. We appreciate your patience.",
        "question_prompt": "What does this notice mainly explain?",
        "options": ["A price increase", "Longer delivery times", "A store closing", "A refund policy"],
        "correct_index": 1,
        "explanation": "The notice states delivery times are now \"7-10 business days instead of the usual 3-5\" — longer than normal.",
    },
    {
        "passage": "Neither the manager nor the assistants ___ available to answer questions this afternoon.",
        "question_prompt": "Choose the word that best completes the sentence.",
        "options": ["is", "was", "are", "be"],
        "correct_index": 2,
        "explanation": "With \"neither...nor,\" the verb agrees with the noun closer to it — \"assistants\" is plural, so \"are\" is correct.",
    },
    {
        "passage": "To: All Staff\nSubject: Parking Lot Closure\nThe west parking lot will be closed for repaving from June 3 to June 5. Please use the east lot during this period. We apologize for any inconvenience.",
        "question_prompt": "What should staff do from June 3 to June 5?",
        "options": ["Avoid coming to work", "Park in the east lot", "Use public transportation only", "Report to a different building"],
        "correct_index": 1,
        "explanation": "The memo directly instructs staff to \"use the east lot during this period\" while the west lot is repaved.",
    },
]


class Command(BaseCommand):
    help = "Seed the original 'TOEIC Practice 1' mock exam (20 questions, Listening + Reading)."

    def handle(self, *args, **options):
        with transaction.atomic():
            exam, _ = MockExam.objects.update_or_create(
                slug=EXAM_SLUG,
                defaults={
                    "title": "Learning Skills TOEIC Practice Test 1",
                    "description": "20 original TOEIC-style questions covering Listening and Reading. "
                    "A shorter practice set, not the full 200-question official length.",
                    "time_limit_minutes": 25,
                    "is_published": True,
                    "sort_order": 1,
                },
            )
            MockExamQuestion.objects.filter(exam=exam).delete()

            order = 1
            for item in LISTENING_QUESTIONS:
                MockExamQuestion.objects.create(exam=exam, section="listening", order=order, **item)
                order += 1
            for item in READING_QUESTIONS:
                MockExamQuestion.objects.create(exam=exam, section="reading", order=order, **item)
                order += 1

        self.stdout.write(self.style.SUCCESS(f"Seeded '{exam.title}' with {exam.question_count} questions."))
