"""Speaking tutor replies — Ollama when available, smart fallbacks otherwise."""

from __future__ import annotations

import json
import os
import random

import httpx

# ---------------------------------------------------------------------------
# Conversation limits
# ---------------------------------------------------------------------------
MAX_HISTORY_TURNS = 10  # user + assistant message pairs count toward this cap

# ---------------------------------------------------------------------------
# Shared tutor rules (appended to every persona system prompt)
# ---------------------------------------------------------------------------
ENGAGEMENT_RULES = """
ENGAGEMENT — this is your top priority, above everything else:
- Read the learner's last message carefully. They are answering YOUR previous question.
- React to something SPECIFIC they said (a detail, place, time, person, action, or opinion).
- Show you heard them: briefly acknowledge their point before your follow-up.
- Stay on the SAME topic thread. Deepen the conversation — do NOT jump to a new unrelated question.
- Never give a vague reply like "That's interesting" or "Good job" without referencing what they actually said.
- If speech-to-text garbled their words, infer the most likely meaning and respond to that.

EXAMPLE — tutor asked: "What does your morning at work look like?"
Learner said: "I wake up at seven and first I check my email"
GOOD: "Seven a.m. — that's early! What do you usually do right after checking email?"
BAD: "That's interesting. Can you tell me more?" (too vague — ignores their answer)
BAD: "What's your favorite hobby?" (ignores the question thread entirely)
""".strip()

SHARED_TUTOR_RULES = """
ROLE: You are an English speaking tutor helping a learner prepare for the TOEIC exam.

TOPICS — stay within TOEIC-relevant situations only:
workplace (meetings, emails, deadlines, colleagues), travel (airports, hotels, directions),
dining and shopping, scheduling appointments, everyday professional small talk.
If the learner goes off-topic (sports, politics, personal drama, fiction), gently redirect:
acknowledge briefly, then steer back to a practice scenario. Never refuse or break character.

CORRECTION — when the learner makes a grammar or vocabulary mistake:
- Do NOT lecture or list rules.
- Naturally model the corrected form inside your reply (e.g. "So you went to the meeting early — was it in person?").
- Correct at most one main error per turn; ignore minor slips if meaning is clear.
- Your correction must still engage with what they said — never correct in isolation.

LENGTH — this reply will be read aloud via text-to-speech:
- Maximum 2 short sentences, roughly 25 words total.
- Sound like natural spoken English, not an essay.
- End with one follow-up question that continues the SAME topic.
""".strip()

REPLY_CHECKLIST = """
Before you reply, silently check:
1. Did I reference something specific from the learner's last message?
2. Am I continuing the same topic, not starting a new one?
3. Is my follow-up question a natural next step from what they told me?
""".strip()

# ---------------------------------------------------------------------------
# Persona system prompts — tune these without touching conversation logic
# ---------------------------------------------------------------------------
MILES_PERSONA = """
You are Miles, a relaxed and encouraging male English tutor.
Your tone is warm, casual, and direct — like a friendly coworker helping someone practice.
You use simple, clear language, contractions, and brief encouragement ("Nice!", "Good stuff", "Got it").
You keep energy upbeat but never pushy. You sound natural, not robotic.
""".strip()

MAYA_PERSONA = """
You are Maya, a warm and structured female English tutor.
Your tone is professional yet approachable — like a patient coach in a language lab.
You speak clearly and calmly, with slightly more formal phrasing than casual chat.
You use supportive framing ("Let's try…", "That's a good start", "I'd suggest…").
You guide the learner step by step without sounding stiff or academic.
""".strip()

TUTOR_PERSONAS = {
    "Miles": MILES_PERSONA,
    "Maya": MAYA_PERSONA,
}

# Difficulty bands keyed to the Speaking skill's own CEFR sub-level
# (UserSkillProgress.cefr_level for skill="speaking") — Phase 1 deliberately
# switched this from the account-global XP level to Speaking's own assessed
# level. Draft copy below — wording per band is a content/pedagogy call, not
# finalized; revisit before relying on it.
LEVEL_DIFFICULTY_GUIDANCE = {
    "A1": (
        "Learner level: A1 (CEFR beginner). "
        "Use very simple vocabulary and short sentences. "
        "Focus on basic workplace greetings, simple requests, and everyday travel phrases."
    ),
    "A2": (
        "Learner level: A2 (CEFR elementary). "
        "Use simple, everyday vocabulary with short, clear sentences. "
        "Focus on routine workplace and travel exchanges — introductions, simple scheduling, basic directions."
    ),
    "B1": (
        "Learner level: B1 (CEFR intermediate). "
        "Use everyday professional English. "
        "Include common office and travel scenarios: scheduling, directions, ordering, short updates."
    ),
    "B2": (
        "Learner level: B2 (CEFR upper-intermediate). "
        "Use more natural, varied phrasing. "
        "Discuss meetings, deadlines, customer service, and multi-step travel situations."
    ),
    "C1": (
        "Learner level: C1 (CEFR advanced). "
        "Use nuanced, TOEIC Part 3–4 style discourse. "
        "Include opinions, brief explanations, and polite professional register — still keep replies short."
    ),
    "C2": (
        "Learner level: C2 (CEFR proficient). "
        "Use idiomatic, natural native-level phrasing with subtle register shifts. "
        "Discuss abstract or nuanced professional topics — still keep replies short and spoken-sounding."
    ),
}

STARTER_QUESTIONS = {
    "Miles": [
        "Hey, I'm Miles. Let's warm up — what does a typical morning at work look like for you?",
        "Hi, I'm Miles. Imagine you're at the airport — where would you be flying and why?",
        "Hey there. Tell me about a meeting or call you had recently — how did it go?",
        "I'm Miles. Quick one — if a colleague asked you to cover their shift, how would you reply?",
    ],
    "Maya": [
        "Hi, I'm Maya. Could you describe how you usually get to work or start your workday?",
        "Hello, I'm Maya. Let's practice travel English — tell me about a trip you've taken or plan to take.",
        "Hi, I'm Maya. How would you politely ask a coworker to send you a document by email?",
        "Hello. Imagine you're ordering lunch with colleagues — what would you say to the server?",
    ],
}

FOLLOW_UPS = [
    "That's interesting. Can you tell me a bit more?",
    "Nice answer. Why do you feel that way?",
    "Good job. Can you give me a specific example?",
    "I like that. What happened next?",
    "Well said. How would you explain that to a friend?",
]


def _last_assistant_message(history: list[dict]) -> str | None:
    for item in reversed(history):
        if item.get("role") == "assistant":
            content = str(item.get("content", "")).strip()
            if content:
                return content
    return None


def _wrap_learner_turn(user_message: str, history: list[dict]) -> str:
    """
    Frame the learner's speech-to-text output so smaller models attend to context.
    The raw user message is still passed as the final user turn for Ollama.
    """
    last_question = _last_assistant_message(history)
    text = user_message.strip()
    if not last_question:
        return text

    return (
        f'You asked: "{last_question}"\n'
        f'The learner answered (speech-to-text, may contain errors): "{text}"\n'
        "Respond directly to their answer. Mention at least one specific detail they shared, "
        "then ask one short follow-up on the same topic."
    )


def build_system_prompt(character: str, *, cefr_level: str | None, error_context: str = "") -> str:
    """
    Assemble the full Ollama system prompt for a tutor persona and learner level.

    cefr_level is Speaking's own per-skill CEFR level (UserSkillProgress for
    skill="speaking") — deliberately NOT the account-global derived level.
    None (not yet assessed — a new speaker, or too few graded turns) falls
    back to A1, the safest floor.

    error_context is the formatted top-N recurring-error block from
    tutor_memory.format_error_context_for_prompt() — shared data source for
    both Miles and Maya (a student's recurring mistakes belong to the
    student, not to whichever persona is currently selected). Empty string
    (the common case — most students have no qualifying patterns yet) is
    simply omitted from assembly, not rendered as an empty section.
    """
    persona = TUTOR_PERSONAS.get(character, MILES_PERSONA)
    difficulty = LEVEL_DIFFICULTY_GUIDANCE.get(cefr_level, LEVEL_DIFFICULTY_GUIDANCE["A1"])
    sections = [persona, ENGAGEMENT_RULES, SHARED_TUTOR_RULES]
    if error_context:
        sections.append(error_context)
    sections.append(difficulty)
    sections.append(REPLY_CHECKLIST)
    return "\n\n".join(sections)


def ollama_available() -> bool:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        response = httpx.get(f"{url}/api/tags", timeout=2.0)
        return response.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _ollama_reply(
    character: str,
    user_message: str,
    history: list[dict],
    *,
    cefr_level: str | None,
    error_context: str = "",
) -> str | None:
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    system_prompt = build_system_prompt(character, cefr_level=cefr_level, error_context=error_context)
    framed_user = _wrap_learner_turn(user_message, history)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-MAX_HISTORY_TURNS:])
    messages.append({"role": "user", "content": framed_user})

    try:
        response = httpx.post(
            f"{url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.75,
                    "top_p": 0.9,
                    "num_predict": 90,
                },
            },
            timeout=45.0,
        )
        if response.status_code != 200:
            return None
        content = response.json().get("message", {}).get("content", "").strip()
        return content or None
    except (httpx.HTTPError, OSError, json.JSONDecodeError, KeyError):
        return None


def _fallback_reply(user_message: str, history: list[dict] | None = None) -> str:
    text = user_message.strip()
    if not text:
        return "I didn't catch that. Could you try again?"

    history = history or []
    last_question = _last_assistant_message(history)
    words = [w.strip(".,!?") for w in text.split() if len(w.strip(".,!?")) > 3]
    detail = words[0] if words else text.split()[0] if text.split() else "that"

    if last_question and len(text.split()) >= 3:
        return (
            f"You mentioned {detail} — that connects to what you said. "
            f"What happened next?"
        )
    if len(text.split()) < 4:
        return random.choice(FOLLOW_UPS)
    return (
        f"You said \"{text[:100]}\" — tell me more about {detail}."
    )


def starter_question(character: str) -> str:
    choices = STARTER_QUESTIONS.get(character, STARTER_QUESTIONS["Miles"])
    return random.choice(choices)


def tutor_reply(
    character: str,
    user_message: str,
    history: list[dict],
    *,
    cefr_level: str | None = None,
    error_context: str = "",
) -> dict:
    character = character if character in TUTOR_PERSONAS else "Miles"
    reply = _ollama_reply(character, user_message, history, cefr_level=cefr_level, error_context=error_context)
    engine = "ollama" if reply else "builtin"
    if not reply:
        reply = _fallback_reply(user_message, history)
    return {"reply": reply, "engine": engine}
