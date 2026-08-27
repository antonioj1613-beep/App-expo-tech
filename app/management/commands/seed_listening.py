"""
Seed the full 15-level TOEIC listening catalog into SkillLesson.

Replaces the entire existing Listening catalog on every run (--replace
semantics, always on), mirroring seed_vocabulary_lessons.py: deletes all
SkillLesson rows for skill=listening first, then recreates the full 60-item
set below via a per-item create() loop (keeps the post_save signal that
syncs Skill.total_lessons — see signals.sync_skill_lesson_count).

Four item types:
- P1: photograph description — passage blank, learner picks the statement
  that best describes a photo. `image_query` (popped before create()) is
  resolved to a real stock photo via stock_image_service.get_stock_image()
  when PEXELS_API_KEY is set; left blank otherwise (no fabricated URL).
- P2: question-response — passage is one spoken question line.
- P3: short conversation. P4: monologue/talk.
`passage` doubles as both the on-screen transcript and the text read aloud
by the browser's speechSynthesis TTS — no separate audio-script field.

Level -> CEFR band matches gamification.LESSON_LEVEL_TO_CEFR_BAND exactly:
1-2 A1, 3-4 A2, 5-7 B1, 8-9 B2, 10-12 C1, 13-15 C2.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from app.models import Skill, SkillLesson
from app.stock_image_service import get_stock_image

PHOTO_PROMPT = "Look at the picture. Choose the statement that best describes it."
RESPONSE_PROMPT = "Choose the best response to what you hear."

LISTENING_LESSON_SEED = [
    # --- Level 1 -- A1 -----------------------------------------------------
    {"title": "Photo: at a café", "passage": "", "question_prompt": PHOTO_PROMPT,
     "options": ["A man is reading a newspaper.", "A woman is ordering a coffee.", "Two people are cooking.", "A child is sleeping."],
     "correct_index": 1, "level": 1, "image_query": "person ordering coffee at counter"},
    {"title": "Question-response: what time is it", "passage": "What time is it?", "question_prompt": RESPONSE_PROMPT,
     "options": ["It's 10 minutes.", "It's three o'clock.", "I'm fine, thanks.", "It's on the table."], "correct_index": 1, "level": 1},
    {"title": "Question-response: nearest bank", "passage": "Where is the nearest bank?", "question_prompt": RESPONSE_PROMPT,
     "options": ["It's next to the pharmacy.", "I'm not hungry.", "Yes, I like it.", "At 9 a.m."], "correct_index": 0, "level": 1},
    {"title": "Coffee shop order", "passage": "Barista: Good morning! What can I get for you today?\nCustomer: Hi, could I have a medium latte, please?\nBarista: Sure. Would you like that hot or iced?\nCustomer: Hot, please. And can I add an extra shot?\nBarista: Of course. That'll be four fifty.\nCustomer: Here you go. Thanks!",
     "question_prompt": "What drink does the customer order?",
     "options": ["A small cappuccino", "A medium latte with an extra shot", "An iced tea", "A large hot chocolate"], "correct_index": 1, "level": 1},

    # --- Level 2 -- A1 -----------------------------------------------------
    {"title": "Photo: at the gym", "passage": "", "question_prompt": PHOTO_PROMPT,
     "options": ["A man is running on a treadmill.", "A woman is swimming.", "People are playing chess.", "A man is sleeping on a bench."],
     "correct_index": 0, "level": 2, "image_query": "person running on treadmill in gym"},
    {"title": "Question-response: pass the salt", "passage": "Could you pass me the salt, please?", "question_prompt": RESPONSE_PROMPT,
     "options": ["Sure, here you go.", "I don't like salt.", "It's Tuesday.", "Yes, I did."], "correct_index": 0, "level": 2},
    {"title": "Question-response: how was your weekend", "passage": "How was your weekend?", "question_prompt": RESPONSE_PROMPT,
     "options": ["It's over there.", "It was really relaxing, thanks.", "Two o'clock.", "No, I haven't."], "correct_index": 1, "level": 2},
    {"title": "Asking for directions", "passage": "Tourist: Excuse me, how do I get to the train station from here?\nLocal: Go straight for two blocks, then turn left at the traffic lights.\nTourist: Is it a long walk?\nLocal: About ten minutes. You'll see the station on your right after the bridge.\nTourist: Perfect, thank you so much!",
     "question_prompt": "Where should the tourist turn?",
     "options": ["Right at the bridge", "Left at the traffic lights", "Right at the coffee shop", "Left after the station"], "correct_index": 1, "level": 2},

    # --- Level 3 -- A2 -----------------------------------------------------
    {"title": "Photo: in a meeting room", "passage": "", "question_prompt": PHOTO_PROMPT,
     "options": ["Two colleagues are shaking hands.", "A man is eating lunch alone.", "A woman is painting a wall.", "Two people are arguing loudly."],
     "correct_index": 0, "level": 3, "image_query": "colleagues shaking hands in office"},
    {"title": "Question-response: tea or coffee", "passage": "Would you like tea or coffee?", "question_prompt": RESPONSE_PROMPT,
     "options": ["Coffee, please.", "It's raining outside.", "I work in sales.", "Yes, I agree."], "correct_index": 0, "level": 3},
    {"title": "Doctor's appointment", "passage": "Receptionist: Good afternoon, Dr. Patel's office. How can I help?\nPatient: Hi, I'd like to book an appointment. I've had a sore throat for three days.\nReceptionist: We have an opening tomorrow at 2:30 p.m. Does that work?\nPatient: Yes, that's fine.\nReceptionist: Great. Please bring your insurance card with you.",
     "question_prompt": "Why is the patient calling?",
     "options": ["To cancel an appointment", "To request a prescription refill", "To book an appointment for a sore throat", "To ask about insurance coverage"], "correct_index": 2, "level": 3},
    {"title": "Returning a purchase", "passage": "Customer: Hi, I'd like to return this jacket. It doesn't fit.\nClerk: No problem. Do you have the receipt?\nCustomer: Yes, here it is.\nClerk: Great, I can offer a refund or an exchange for a different size.\nCustomer: I'll take a refund, please.",
     "question_prompt": "What does the customer want?",
     "options": ["A different color", "A refund", "A gift card", "To keep the jacket"], "correct_index": 1, "level": 3},

    # --- Level 4 -- A2 -----------------------------------------------------
    {"title": "Photo: at the airport check-in", "passage": "", "question_prompt": PHOTO_PROMPT,
     "options": ["A traveler is checking in luggage.", "A pilot is flying a plane.", "Passengers are boarding a bus.", "A man is sleeping in a chair."],
     "correct_index": 0, "level": 4, "image_query": "traveler checking in luggage at airport counter"},
    {"title": "Question-response: report due date", "passage": "Do you know when the report is due?", "question_prompt": RESPONSE_PROMPT,
     "options": ["By Friday afternoon.", "It's blue.", "I like tea.", "He's my colleague."], "correct_index": 0, "level": 4},
    {"title": "Question-response: send the file", "passage": "Can you send me the file before lunch?", "question_prompt": RESPONSE_PROMPT,
     "options": ["Sure, I'll send it now.", "I had a sandwich.", "It's on the second floor.", "Yes, I did that yesterday."], "correct_index": 0, "level": 4},
    {"title": "Job interview introduction", "passage": "Interviewer: Thanks for coming in today. Tell me a little about yourself.\nCandidate: I'm a project coordinator with four years of experience in tech. I manage timelines and keep teams aligned.\nInterviewer: What attracted you to this role?\nCandidate: I enjoy solving problems and working with cross-functional teams. Your company's focus on learning really stood out to me.",
     "question_prompt": "What is the candidate's current role?",
     "options": ["Software engineer", "Project coordinator", "Marketing manager", "Customer support lead"], "correct_index": 1, "level": 4},

    # --- Level 5 -- B1 (Part 4 talks begin) --------------------------------
    {"title": "Question-response: conference presenters", "passage": "Who's presenting at the conference this year?", "question_prompt": RESPONSE_PROMPT,
     "options": ["Two new speakers were invited.", "It's in London.", "I bought a ticket.", "Next Tuesday."], "correct_index": 0, "level": 5},
    {"title": "Morning routine podcast", "passage": "Host: Welcome back to Daily Habits. Today we're talking about morning routines that actually stick.\nGuest: The key is starting small. Even five minutes of stretching or journaling can set a positive tone for the day.\nHost: So you don't need a two-hour ritual to see results?\nGuest: Exactly. Consistency matters more than complexity.",
     "question_prompt": "According to the guest, what matters most?",
     "options": ["Waking up before sunrise", "A two-hour morning ritual", "Consistency over complexity", "Avoiding all screen time"], "correct_index": 2, "level": 5},
    {"title": "Booking a hotel room", "passage": "Guest: Hi, I'd like to book a room for two nights next weekend.\nClerk: Sure, would you prefer a single or double room?\nGuest: A double, please, with a city view if possible.\nClerk: We have one available. That'll be confirmed by email shortly.",
     "question_prompt": "What kind of room does the guest request?",
     "options": ["A single room with no view", "A double room with a city view", "A suite with a kitchen", "A room near the pool"], "correct_index": 1, "level": 5},
    {"title": "Store announcement", "passage": "Attention shoppers: our store will be closing in fifteen minutes. Please bring your final selections to the checkout counters at the front of the store. We thank you for shopping with us today and look forward to seeing you again soon.",
     "question_prompt": "What is the announcement mainly about?",
     "options": ["A sale starting soon", "The store closing soon", "A lost child", "A new product launch"], "correct_index": 1, "level": 5},

    # --- Level 6 -- B1 -------------------------------------------------------
    {"title": "Scheduling a call", "passage": "Alex: Are you free for a quick call this afternoon?\nJordan: I have a meeting until 3, but I'm open after that.\nAlex: Perfect, let's do 3:30.\nJordan: Sounds good, I'll send a calendar invite.",
     "question_prompt": "When will Alex and Jordan have their call?",
     "options": ["Before 3 p.m.", "At 3:30 p.m.", "Tomorrow morning", "During the meeting"], "correct_index": 1, "level": 6},
    {"title": "Ordering office supplies", "passage": "Employee: We're almost out of printer paper and pens.\nOffice Manager: I'll place an order today. Do we need anything else?\nEmployee: Maybe some more notebooks for the training session.\nOffice Manager: Good idea, I'll add those too.",
     "question_prompt": "What will the office manager order, besides paper and pens?",
     "options": ["Notebooks", "Chairs", "Coffee", "A new printer"], "correct_index": 0, "level": 6},
    {"title": "Flight boarding announcement", "passage": "We are now boarding Flight 204 to Chicago. Passengers seated in rows 20 through 35, please proceed to gate 12B. Passengers requiring extra assistance may board at this time as well. Please have your boarding pass ready.",
     "question_prompt": "Who is invited to board first, according to the announcement?",
     "options": ["Passengers in rows 1 through 19", "Passengers requiring extra assistance", "Only first class passengers", "Passengers with connecting flights"], "correct_index": 1, "level": 6},
    {"title": "Museum tour introduction", "passage": "Welcome to the Maritime Museum. Our guided tour begins in five minutes at the main entrance. The tour lasts approximately ninety minutes and covers three exhibit halls. Photography is permitted, but please turn off camera flashes near the older artifacts.",
     "question_prompt": "How long does the tour last?",
     "options": ["Five minutes", "Thirty minutes", "Ninety minutes", "Three hours"], "correct_index": 2, "level": 6},

    # --- Level 7 -- B1 (first multi-question set) -----------------------------
    {"title": "Team lunch planning (1/2)", "passage": "Sam: Should we order lunch for the team meeting on Friday?\nRiley: Good idea. What does everyone usually like?\nSam: Let's do a mix — maybe sandwiches and a couple of salads.\nRiley: I'll email around to check for allergies first, then place the order Thursday.",
     "question_prompt": "What will Riley do before ordering?",
     "options": ["Book a restaurant", "Check for allergies", "Cancel the meeting", "Pay the bill"], "correct_index": 1, "level": 7},
    {"title": "Team lunch planning (2/2)", "passage": "Sam: Should we order lunch for the team meeting on Friday?\nRiley: Good idea. What does everyone usually like?\nSam: Let's do a mix — maybe sandwiches and a couple of salads.\nRiley: I'll email around to check for allergies first, then place the order Thursday.",
     "question_prompt": "When does Riley plan to place the order?",
     "options": ["Friday morning", "Wednesday", "Thursday", "During the meeting"], "correct_index": 2, "level": 7},
    {"title": "Weather report", "passage": "And now for today's weather: expect cloudy skies this morning, clearing up by early afternoon with highs near twenty degrees. A light breeze is expected from the west. Tomorrow looks similar, with a slight chance of rain in the evening.",
     "question_prompt": "What will the weather be like by early afternoon?",
     "options": ["Rainy", "Clearing up", "Snowing", "Very windy"], "correct_index": 1, "level": 7},
    {"title": "Voicemail from a colleague", "passage": "Hi, it's Dana. I'm calling about tomorrow's presentation — could you send me the final slides tonight if possible? I'd like to review them before the client call at nine. Thanks, talk soon.",
     "question_prompt": "What does Dana ask for?",
     "options": ["A rescheduled meeting", "The final slides", "A ride to the office", "Feedback on a report"], "correct_index": 1, "level": 7},

    # --- Level 8 -- B2 ----------------------------------------------------------
    {"title": "Budget discussion (1/2)", "passage": "Manager: We're slightly over budget for this quarter's marketing spend.\nAnalyst: Most of it came from the trade show booth and travel.\nManager: Can we scale back the next campaign to balance it out?\nAnalyst: I think so — I'll revise the numbers and send an updated forecast tomorrow.",
     "question_prompt": "What caused most of the overspending?",
     "options": ["Office supplies", "The trade show booth and travel", "Software licenses", "Employee salaries"], "correct_index": 1, "level": 8},
    {"title": "Budget discussion (2/2)", "passage": "Manager: We're slightly over budget for this quarter's marketing spend.\nAnalyst: Most of it came from the trade show booth and travel.\nManager: Can we scale back the next campaign to balance it out?\nAnalyst: I think so — I'll revise the numbers and send an updated forecast tomorrow.",
     "question_prompt": "What will the analyst do next?",
     "options": ["Cancel the campaign entirely", "Hire a new analyst", "Revise the numbers and send a forecast", "Approve the current budget"], "correct_index": 2, "level": 8},
    {"title": "Company all-hands recording", "passage": "Thank you all for joining today's all-hands meeting. This quarter, we exceeded our sales target by twelve percent, largely thanks to the new customer onboarding process. Looking ahead, we'll be expanding the support team to keep pace with demand. More details will follow in next week's department meetings.",
     "question_prompt": "Why did the company exceed its sales target?",
     "options": ["A new advertising campaign", "The new customer onboarding process", "Lower prices", "A merger"], "correct_index": 1, "level": 8},
    {"title": "Train delay announcement", "passage": "We apologize for the delay to the 8:15 service to Riverside. Due to a signal issue, the train will now depart at approximately 8:40. We appreciate your patience and will provide updates as they become available.",
     "question_prompt": "Why is the train delayed?",
     "options": ["Bad weather", "A signal issue", "Not enough staff", "A mechanical failure"], "correct_index": 1, "level": 8},

    # --- Level 9 -- B2 ------------------------------------------------------------
    {"title": "Product launch briefing (1/2)", "passage": "Good morning, team. Today I want to walk you through the timeline for next month's product launch. Marketing materials need final approval by the 10th, and the press release goes out on the 15th. The website update should go live the same day as the press release, so please flag any blockers to me by end of week.",
     "question_prompt": "When do marketing materials need final approval?",
     "options": ["The 5th", "The 10th", "The 15th", "End of the month"], "correct_index": 1, "level": 9},
    {"title": "Product launch briefing (2/2)", "passage": "Good morning, team. Today I want to walk you through the timeline for next month's product launch. Marketing materials need final approval by the 10th, and the press release goes out on the 15th. The website update should go live the same day as the press release, so please flag any blockers to me by end of week.",
     "question_prompt": "What should happen on the same day as the press release?",
     "options": ["The marketing approval", "The website update goes live", "A team meeting", "The product ships"], "correct_index": 1, "level": 9},
    {"title": "Requesting feedback", "passage": "Employee: Do you have a few minutes to look over my draft proposal?\nManager: Sure, send it over and I'll review it this afternoon.\nEmployee: Thanks, I really want to make sure the numbers are solid before the client sees it.\nManager: No problem, I'll flag anything that needs adjusting.",
     "question_prompt": "What is the employee most concerned about?",
     "options": ["The formatting", "The numbers being accurate", "The client's schedule", "The length of the document"], "correct_index": 1, "level": 9},
    {"title": "IT support call", "passage": "Employee: My laptop won't connect to the office Wi-Fi this morning.\nIT Support: Let's try restarting it first. If that doesn't work, I can reset your network settings remotely.\nEmployee: Okay, restarting now... still not working.\nIT Support: Alright, give me a moment to reset it from my end.",
     "question_prompt": "What does IT support offer to do if restarting doesn't fix the issue?",
     "options": ["Send a new laptop", "Reset the network settings remotely", "Schedule an in-person visit", "Cancel the meeting"], "correct_index": 1, "level": 9},

    # --- Level 10 -- C1 (first 3-question set) --------------------------------------
    {"title": "Quarterly strategy briefing (1/3)", "passage": "As we head into the next quarter, I want to highlight three priorities. First, we're doubling down on our enterprise client segment, which has shown the strongest growth this year. Second, we're investing in customer support infrastructure to handle the increased volume. Third, we're pausing expansion into new regions until the current markets stabilize. Questions can be directed to your team leads.",
     "question_prompt": "Which client segment is the company focusing on?",
     "options": ["Small business clients", "Enterprise clients", "International clients only", "Government clients"], "correct_index": 1, "level": 10},
    {"title": "Quarterly strategy briefing (2/3)", "passage": "As we head into the next quarter, I want to highlight three priorities. First, we're doubling down on our enterprise client segment, which has shown the strongest growth this year. Second, we're investing in customer support infrastructure to handle the increased volume. Third, we're pausing expansion into new regions until the current markets stabilize. Questions can be directed to your team leads.",
     "question_prompt": "Why is the company investing in support infrastructure?",
     "options": ["To reduce staff", "To handle increased volume", "To close a regional office", "To launch a new product"], "correct_index": 1, "level": 10},
    {"title": "Quarterly strategy briefing (3/3)", "passage": "As we head into the next quarter, I want to highlight three priorities. First, we're doubling down on our enterprise client segment, which has shown the strongest growth this year. Second, we're investing in customer support infrastructure to handle the increased volume. Third, we're pausing expansion into new regions until the current markets stabilize. Questions can be directed to your team leads.",
     "question_prompt": "What has the company decided to pause?",
     "options": ["Enterprise sales", "Customer support hiring", "Expansion into new regions", "The quarterly briefing"], "correct_index": 2, "level": 10},
    {"title": "Contract negotiation call", "passage": "Vendor: We can offer a five percent discount if you commit to a two-year contract.\nBuyer: That's appealing, but I'd need to check with finance before committing that long.\nVendor: Understood — I can hold this offer open for one week.\nBuyer: That works. I'll follow up by Thursday.",
     "question_prompt": "What does the vendor offer?",
     "options": ["A free trial", "A five percent discount for a two-year contract", "A one-year contract with no discount", "A refund"], "correct_index": 1, "level": 10},

    # --- Level 11 -- C1 -----------------------------------------------------------
    {"title": "Vendor dispute call (1/2)", "passage": "Client: We received the wrong shipment again this month — this is the third time.\nSupplier: I sincerely apologize. I'll personally track this shipment and arrange expedited replacement at no cost.\nClient: I appreciate that, but we also need a longer-term fix so this stops happening.\nSupplier: Agreed — I'll schedule a call with our warehouse team to review the process this week.",
     "question_prompt": "How many times has this shipment error happened?",
     "options": ["Once", "Twice", "Three times", "It's the first time"], "correct_index": 2, "level": 11},
    {"title": "Vendor dispute call (2/2)", "passage": "Client: We received the wrong shipment again this month — this is the third time.\nSupplier: I sincerely apologize. I'll personally track this shipment and arrange expedited replacement at no cost.\nClient: I appreciate that, but we also need a longer-term fix so this stops happening.\nSupplier: Agreed — I'll schedule a call with our warehouse team to review the process this week.",
     "question_prompt": "What will the supplier do this week?",
     "options": ["Cancel the contract", "Schedule a call with the warehouse team", "Raise prices", "Ignore the complaint"], "correct_index": 1, "level": 11},
    {"title": "Investor call excerpt (1/2)", "passage": "Turning to our outlook for next year, we anticipate continued margin pressure from input costs, partially offset by pricing adjustments implemented last quarter. We remain committed to our long-term growth targets, though we're taking a more conservative approach to capital expenditure in the near term.",
     "question_prompt": "What is putting pressure on margins?",
     "options": ["Lower demand", "Input costs", "A new competitor", "Currency exchange rates"], "correct_index": 1, "level": 11},
    {"title": "Investor call excerpt (2/2)", "passage": "Turning to our outlook for next year, we anticipate continued margin pressure from input costs, partially offset by pricing adjustments implemented last quarter. We remain committed to our long-term growth targets, though we're taking a more conservative approach to capital expenditure in the near term.",
     "question_prompt": "What approach is the company taking toward capital expenditure?",
     "options": ["Aggressive expansion", "A more conservative approach", "Complete elimination", "No change from last year"], "correct_index": 1, "level": 11},

    # --- Level 12 -- C1 -------------------------------------------------------------
    {"title": "Risk management briefing (1/3)", "passage": "This briefing covers our updated risk framework. First, supply chain risk remains elevated due to ongoing geopolitical tensions, and we've diversified our supplier base accordingly. Second, cybersecurity risk has grown with our expanded remote workforce, prompting a new mandatory training rollout next month. Third, regulatory risk in our European operations requires close monitoring given upcoming policy changes.",
     "question_prompt": "Why does supply chain risk remain elevated?",
     "options": ["Weak demand", "Geopolitical tensions", "A shortage of staff", "Currency fluctuations"], "correct_index": 1, "level": 12},
    {"title": "Risk management briefing (2/3)", "passage": "This briefing covers our updated risk framework. First, supply chain risk remains elevated due to ongoing geopolitical tensions, and we've diversified our supplier base accordingly. Second, cybersecurity risk has grown with our expanded remote workforce, prompting a new mandatory training rollout next month. Third, regulatory risk in our European operations requires close monitoring given upcoming policy changes.",
     "question_prompt": "What is prompting the new mandatory training?",
     "options": ["A customer complaint", "Increased cybersecurity risk from remote work", "A change in company logo", "A merger"], "correct_index": 1, "level": 12},
    {"title": "Risk management briefing (3/3)", "passage": "This briefing covers our updated risk framework. First, supply chain risk remains elevated due to ongoing geopolitical tensions, and we've diversified our supplier base accordingly. Second, cybersecurity risk has grown with our expanded remote workforce, prompting a new mandatory training rollout next month. Third, regulatory risk in our European operations requires close monitoring given upcoming policy changes.",
     "question_prompt": "Where does regulatory risk require close monitoring?",
     "options": ["Asia-Pacific operations", "European operations", "Domestic operations only", "Supply chain operations"], "correct_index": 1, "level": 12},
    {"title": "Performance review discussion", "passage": "Manager: Overall, this has been a strong year — your project delivery has been consistently on time.\nEmployee: Thank you, I've been focused on improving my planning process.\nManager: It shows. One area to keep developing is delegating more to junior team members.\nEmployee: That's fair, I'll work on that next quarter.",
     "question_prompt": "What area does the manager suggest improving?",
     "options": ["Meeting deadlines", "Delegating to junior team members", "Written communication", "Attendance"], "correct_index": 1, "level": 12},

    # --- Level 13 -- C2 -----------------------------------------------------------------
    {"title": "Earnings call Q&A (1/3)", "passage": "Analyst: Can you elaborate on the drivers behind the margin compression this quarter?\nCFO: Certainly. The primary driver was elevated freight costs, which we expect to normalize by mid-year as new shipping contracts take effect. We've also accelerated procurement diversification to reduce our exposure to any single supplier region.\nAnalyst: And is that diversification affecting unit costs in the near term?\nCFO: Marginally, yes, but we view it as a worthwhile trade-off for long-term supply resilience.",
     "question_prompt": "What was the primary driver of margin compression?",
     "options": ["Lower sales volume", "Elevated freight costs", "A currency devaluation", "Increased marketing spend"], "correct_index": 1, "level": 13},
    {"title": "Earnings call Q&A (2/3)", "passage": "Analyst: Can you elaborate on the drivers behind the margin compression this quarter?\nCFO: Certainly. The primary driver was elevated freight costs, which we expect to normalize by mid-year as new shipping contracts take effect. We've also accelerated procurement diversification to reduce our exposure to any single supplier region.\nAnalyst: And is that diversification affecting unit costs in the near term?\nCFO: Marginally, yes, but we view it as a worthwhile trade-off for long-term supply resilience.",
     "question_prompt": "When does the CFO expect freight costs to normalize?",
     "options": ["Immediately", "By mid-year", "Next year", "They will not normalize"], "correct_index": 1, "level": 13},
    {"title": "Earnings call Q&A (3/3)", "passage": "Analyst: Can you elaborate on the drivers behind the margin compression this quarter?\nCFO: Certainly. The primary driver was elevated freight costs, which we expect to normalize by mid-year as new shipping contracts take effect. We've also accelerated procurement diversification to reduce our exposure to any single supplier region.\nAnalyst: And is that diversification affecting unit costs in the near term?\nCFO: Marginally, yes, but we view it as a worthwhile trade-off for long-term supply resilience.",
     "question_prompt": "How does the CFO characterize the effect of diversification on unit costs?",
     "options": ["A significant increase", "A marginal increase, viewed as worthwhile", "A significant decrease", "No effect at all"], "correct_index": 1, "level": 13},
    {"title": "Cross-departmental disagreement", "passage": "Finance Lead: I understand the urgency, but approving this spend without a formal review sets a difficult precedent.\nProduct Lead: I hear you, but delaying it risks missing the launch window entirely.\nFinance Lead: Let's compromise — I'll expedite a review within 48 hours if you can hold the launch that long.\nProduct Lead: That works, I'll adjust the timeline accordingly.",
     "question_prompt": "What compromise do the two leads reach?",
     "options": ["Cancel the launch", "An expedited 48-hour review", "Approve the spend with no review", "Postpone the launch by a month"], "correct_index": 1, "level": 13},

    # --- Level 14 -- C2 -----------------------------------------------------------------
    {"title": "Panel discussion excerpt (1/3)", "passage": "Moderator: There's a perception that automation primarily threatens entry-level roles. Would you agree?\nPanelist: Not entirely — we're actually seeing more disruption at the mid-management level, where a lot of coordination work is increasingly handled by software.\nModerator: That's a striking distinction. What does that mean for how companies should be training their workforce?\nPanelist: It suggests upskilling efforts should focus less on technical entry points and more on strategic judgment and cross-functional skills that are harder to automate.",
     "question_prompt": "Where does the panelist say disruption is actually concentrated?",
     "options": ["Entry-level roles", "Mid-management roles", "Executive roles only", "It is evenly spread across all levels"], "correct_index": 1, "level": 14},
    {"title": "Panel discussion excerpt (2/3)", "passage": "Moderator: There's a perception that automation primarily threatens entry-level roles. Would you agree?\nPanelist: Not entirely — we're actually seeing more disruption at the mid-management level, where a lot of coordination work is increasingly handled by software.\nModerator: That's a striking distinction. What does that mean for how companies should be training their workforce?\nPanelist: It suggests upskilling efforts should focus less on technical entry points and more on strategic judgment and cross-functional skills that are harder to automate.",
     "question_prompt": "What does the panelist suggest upskilling should focus on?",
     "options": ["Basic technical entry points", "Strategic judgment and cross-functional skills", "Reducing headcount", "Outsourcing management"], "correct_index": 1, "level": 14},
    {"title": "Panel discussion excerpt (3/3)", "passage": "Moderator: There's a perception that automation primarily threatens entry-level roles. Would you agree?\nPanelist: Not entirely — we're actually seeing more disruption at the mid-management level, where a lot of coordination work is increasingly handled by software.\nModerator: That's a striking distinction. What does that mean for how companies should be training their workforce?\nPanelist: It suggests upskilling efforts should focus less on technical entry points and more on strategic judgment and cross-functional skills that are harder to automate.",
     "question_prompt": "What is the moderator's initial assumption?",
     "options": ["Automation mainly threatens entry-level roles", "Automation threatens no one", "Automation only affects executives", "Automation is not a relevant topic"], "correct_index": 0, "level": 14},
    {"title": "Question-response: client pricing pushback", "passage": "If the client pushes back on the pricing again, how should we handle it?", "question_prompt": RESPONSE_PROMPT,
     "options": ["We should hold firm but offer a value-added service instead of a discount.", "The meeting room is on the third floor.", "I already had lunch.", "It's scheduled for next Monday."], "correct_index": 0, "level": 14},

    # --- Level 15 -- C2 -----------------------------------------------------------------
    {"title": "Regulatory briefing excerpt (1/3)", "passage": "Legal Counsel: The proposed amendment would tighten disclosure requirements around related-party transactions, effective the start of next fiscal year. Compliance will need to revise our internal reporting templates well ahead of that deadline to avoid a last-minute scramble.\nCFO: Understood. What's the anticipated burden on the finance team specifically?\nLegal Counsel: Moderate — mainly additional documentation on transactions with affiliated entities, though we don't expect it to affect any existing arrangements substantively.",
     "question_prompt": "What does the proposed amendment tighten?",
     "options": ["Employee benefits", "Disclosure requirements for related-party transactions", "Marketing spending limits", "Import tariffs"], "correct_index": 1, "level": 15},
    {"title": "Regulatory briefing excerpt (2/3)", "passage": "Legal Counsel: The proposed amendment would tighten disclosure requirements around related-party transactions, effective the start of next fiscal year. Compliance will need to revise our internal reporting templates well ahead of that deadline to avoid a last-minute scramble.\nCFO: Understood. What's the anticipated burden on the finance team specifically?\nLegal Counsel: Moderate — mainly additional documentation on transactions with affiliated entities, though we don't expect it to affect any existing arrangements substantively.",
     "question_prompt": "What does Legal Counsel recommend doing well ahead of the deadline?",
     "options": ["Hiring additional staff", "Revising internal reporting templates", "Canceling existing contracts", "Relocating the finance department"], "correct_index": 1, "level": 15},
    {"title": "Regulatory briefing excerpt (3/3)", "passage": "Legal Counsel: The proposed amendment would tighten disclosure requirements around related-party transactions, effective the start of next fiscal year. Compliance will need to revise our internal reporting templates well ahead of that deadline to avoid a last-minute scramble.\nCFO: Understood. What's the anticipated burden on the finance team specifically?\nLegal Counsel: Moderate — mainly additional documentation on transactions with affiliated entities, though we don't expect it to affect any existing arrangements substantively.",
     "question_prompt": "How does Legal Counsel describe the anticipated burden on finance?",
     "options": ["Severe and disruptive", "Moderate, mainly additional documentation", "Nonexistent", "Impossible to estimate"], "correct_index": 1, "level": 15},
    {"title": "Post-merger integration discussion", "passage": "Integration Lead: The two teams' reporting structures are still misaligned three months in — that's slowing decision-making more than I'd like.\nHR Partner: Agreed. I'd recommend we formalize a single reporting line by next quarter rather than continuing with the dual-track arrangement.\nIntegration Lead: That aligns with what I was going to propose. Let's draft the plan together this week.",
     "question_prompt": "What problem does the integration lead raise?",
     "options": ["Budget overruns", "Misaligned reporting structures slowing decisions", "A lack of office space", "Customer complaints"], "correct_index": 1, "level": 15},
]


class Command(BaseCommand):
    help = "Replace the Listening SkillLesson catalog with the full 15-level TOEIC set."

    @transaction.atomic
    def handle(self, *args, **options):
        listening_skill = Skill.objects.filter(slug="listening").first()
        if not listening_skill:
            self.stderr.write(self.style.ERROR("Listening skill not found — run seed_skills first."))
            return

        deleted, _ = SkillLesson.objects.filter(skill=listening_skill).delete()
        self.stdout.write(f"Deleted {deleted} existing row(s) (SkillLesson + cascaded completions).")

        created = 0
        images_found = 0
        used_slugs = set()
        for order, row in enumerate(LISTENING_LESSON_SEED, start=1):
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
                skill=listening_skill,
                slug=slug,
                sort_order=order,
                is_published=True,
                image_url=image_url,
                image_credit=image_credit,
                **row,
            )
            created += 1

        total = SkillLesson.objects.filter(skill=listening_skill).count()
        self.stdout.write(self.style.SUCCESS(
            f"Listening seed complete: {total} lesson(s), {created} created, {images_found} photo(s) resolved."
        ))
