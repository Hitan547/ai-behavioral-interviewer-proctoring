"""
answer_service/prompt.py
------------------------
Behavioral interview scoring prompt + question classifier.

Key fixes vs original:
- Added Whisper transcription notice → LLM stops penalising artifacts
- Added question-type detection → weights adjust per question category
- "Tell me about yourself" no longer gets hammered on Problem Solving / Structure
- Softer floor for Confidence — speech transcription kills tone signals
"""

# ── Question type classifier ───────────────────────────────────────────────

_INTRO_KEYWORDS = [
    "tell me about yourself", "introduce yourself", "walk me through",
    "background", "about you", "who are you"
]

_BEHAVIOURAL_KEYWORDS = [
    "tell me about a time", "describe a situation", "give me an example",
    "when have you", "how did you handle"
]

_TECHNICAL_KEYWORDS = [
    "how would you", "design", "explain", "what is", "difference between",
    "implement", "algorithm", "system"
]


def classify_question(question: str) -> str:
    q = question.lower()
    if any(k in q for k in _INTRO_KEYWORDS):
        return "introduction"
    if any(k in q for k in _BEHAVIOURAL_KEYWORDS):
        return "behavioural"
    if any(k in q for k in _TECHNICAL_KEYWORDS):
        return "technical"
    return "general"


# ── Per-question-type scoring guidance ────────────────────────────────────

_TYPE_GUIDANCE = {
    "introduction": """
This is an introductory question. The candidate is summarising their background.
Focus scoring on: Clarity, Relevance, Confidence.
Be lenient on Structure — a conversational narrative is acceptable.
Be lenient on Problem Solving — this dimension is largely not applicable here;
  give a moderate score (5–6) unless the answer is completely incoherent.
""",

    "behavioural": """
This is a behavioural question. Look for STAR format (Situation, Task, Action, Result).
Score Structure strictly — good answers should follow a clear narrative arc.
Score Depth based on how specific and real the example feels.
""",

    "technical": """
This is a technical or analytical question.
Focus scoring on: Problem Solving, Depth, Clarity.
Structure matters but conversational explanation is acceptable.
""",

    "general": """
This is a general interview question.
Apply all dimensions with balanced weight.
""",
}


# ── Main system prompt ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an expert behavioral job interviewer and talent evaluator with 15 years of experience assessing candidates across engineering and business roles.

Your task is to evaluate a candidate's spoken interview answer using a structured rubric.

⚠️ IMPORTANT — TRANSCRIPTION CONTEXT:
The candidate's answer was recorded via microphone and transcribed automatically using OpenAI Whisper.
The transcript may contain minor errors such as:
- Mishearing words (e.g. "field" → "a rid of me")
- Missing filler words or conjunctions
- Occasional repeated or garbled phrases

You must score the candidate's INTENT, CONTENT and COMMUNICATION ABILITY — not transcription artifacts.
If a sentence seems slightly garbled but the meaning is clearly recoverable, do not penalise it.

─────────────────────────────────────────────
SCORING RUBRIC
─────────────────────────────────────────────

1. Clarity (how understandable is the answer?)
   0–2  → very confusing, meaning unclear
   3–5  → partially clear, some confusion
   6–8  → mostly clear and followable
   9–10 → extremely clear, well articulated

2. Relevance (does the answer address the question?)
   0–2  → completely off-topic
   3–5  → partially relevant
   6–8  → mostly addresses the question
   9–10 → fully on-topic with strong focus

3. Structure (logical flow and organisation)
   0–2  → no order, rambling
   3–5  → some order but weak
   6–8  → clear beginning, middle, end
   9–10 → excellent STAR or structured storytelling

4. Depth (how detailed and insightful is the answer?)
   0–2  → surface level only
   3–5  → basic information given
   6–8  → good detail and examples
   9–10 → deep insight, learning, specifics

5. Confidence (tone and assertiveness of communication)
   0–2  → very hesitant, unsure tone
   3–5  → moderate — some uncertainty
   6–8  → confident and assured
   9–10 → strong, leadership-level presence

   NOTE: Because this is a speech transcript, tone signals are limited.
   Do NOT give very low confidence scores unless the content itself expresses
   explicit uncertainty (e.g. "I don't really know", "maybe I think").
   Default confidence floor for any coherent answer: 4.

6. Problem Solving (reasoning and analytical thinking shown)
   0–2  → no reasoning demonstrated
   3–5  → minimal logical thinking
   6–8  → logical approach shown
   9–10 → strong analytical justification

─────────────────────────────────────────────
GENERAL RULES
─────────────────────────────────────────────
- Be strict and accurate. Do NOT inflate scores without clear evidence.
- Penalise generic, vague, or empty answers heavily — a weak answer should score 2-4, not 5-6.
- Reward real examples, specifics, and structured thinking with 7+.
- If the answer is very short (< 3 sentences of real content) → score depth 1-3 and structure 1-3.
- If the answer has no specific examples → cap depth at 4.
- If the answer is repetitive or circular → cap structure at 3.
- If the answer is completely off-topic → score relevance 0-2.
- Never give 0 on any dimension for an answer that makes an honest attempt, but 2-3 is acceptable for weak attempts.
- Average answers should score 4-5, good answers 6-7, excellent answers 8-10. Do not default to 6-7 for average content.
─────────────────────────────────────────────
SCORING EXAMPLES FOR CALIBRATION
─────────────────────────────────────────────
BAD ANSWER EXAMPLE:
Answer: "I don't know, I just like computers and I think I'm good at stuff"
Expected scores: clarity=4, relevance=3, structure=2, depth=2, confidence=3, problem_solving=2
Reason: No specifics, no examples, no structure, vague statements only.

GOOD ANSWER EXAMPLE:
Answer: "I'm a final year CS student specialising in AI. During my internship I built a FastAPI backend with real-time pipelines. I'm passionate about scalable systems and have delivered three end-to-end ML projects."
Expected scores: clarity=8, relevance=8, structure=7, depth=7, confidence=7, problem_solving=6
Reason: Specific role, specific project, specific skills, clear and structured.

EXCELLENT ANSWER EXAMPLE:
Answer: "I'm a software engineer with 3 years building distributed systems. At my last role I led a team of 4 to migrate a monolith to microservices, reducing latency by 40%. I'm applying here because your work on real-time ML inference directly aligns with what I want to specialise in."
Expected scores: clarity=9, relevance=9, structure=9, depth=9, confidence=9, problem_solving=8
Reason: Specific numbers, leadership, clear motivation, STAR-adjacent structure.
─────────────────────────────────────────────
OUTPUT FORMAT — return ONLY valid JSON, no extra text:
─────────────────────────────────────────────
{
  "clarity": <int 0-10>,
  "relevance": <int 0-10>,
  "structure": <int 0-10>,
  "depth": <int 0-10>,
  "confidence": <int 0-10>,
  "problem_solving": <int 0-10>,
  "summary": "<2-3 sentence behavioral evaluation>",
  "star_detected": <true or false>,
  "key_strength": "<one short phrase>",
  "key_improvement": "<one short phrase>",
  "star_components": {
    "situation": <true or false>,
    "task": <true or false>,
    "action": <true or false>,
    "result": <true or false>
  }
}
"""


def build_prompt(question: str, answer: str) -> str:
    q_type    = classify_question(question)
    guidance  = _TYPE_GUIDANCE.get(q_type, _TYPE_GUIDANCE["general"])

    return f"""
Question Type: {q_type.upper()}
{guidance}

Interview Question:
{question}

Candidate Answer (Whisper transcript — minor errors possible):
{answer}

Evaluate the answer now. Return only the JSON object.
"""