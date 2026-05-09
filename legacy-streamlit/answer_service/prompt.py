"""
answer_service/prompt.py
------------------------
Recruiter-calibrated scoring prompt + question classifier.

Fix applied:
  build_prompt() previously only accepted (question, answer).
  llm_engine.py now calls build_prompt(question, answer, jd_text=jd_text)
  which raised TypeError: build_prompt() got an unexpected keyword argument 'jd_text'
  causing every evaluate_answer() call to silently fall back to 0-scores.
  Added jd_text parameter with empty-string default.
"""

import re

# ── System prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior technical recruiter with 10+ years of experience screening candidates for software engineering, data science, and AI/ML roles.

You are evaluating a candidate's spoken interview answer that was transcribed by Whisper speech-to-text. The transcript may contain minor transcription artifacts (filler words, repeated words, slight mis-transcriptions). Do NOT penalise these — evaluate the underlying substance.

COHERENCE CHECK (CRITICAL — do this FIRST):
Before scoring, assess whether the transcript is coherent and intelligible.
If the transcript contains mostly nonsensical phrases, random word combinations,
or sentences that make no logical sense in context of the question, this indicates
a transcription failure — NOT a bad candidate answer. In this case:
- Set ALL dimension scores to 2 or below
- Set recruiter_verdict to "Borderline" or "Do Not Advance"
- Note in summary: "Transcript appears corrupted/unintelligible — re-record recommended"
Examples of gibberish: "Google Webmaster Planning and Learning", "the Pandas field runs from issue line pickup", "Spindmaik the contents of Big Bang screech"

Score the answer on exactly these 6 dimensions, each from 0 to 10:

1. clarity        — Is the answer easy to follow? Clear structure, logical flow.
2. relevance      — Does it directly address what was asked?
3. star_quality   — Does it follow Situation→Task→Action→Result structure? (For non-behavioural questions, score leniently)
4. specificity    — Are there concrete examples, numbers, technologies, outcomes?
5. communication  — Confidence, vocabulary, professional tone.
6. job_fit        — Does the answer show alignment with the role/JD requirements?

CALIBRATION:
- 8-10 = Would strongly advance. Specific, structured, impressive.
- 6-7  = Would advance. Solid answer with minor gaps.
- 4-5  = Borderline. Some substance but vague or incomplete.
- 2-3  = Weak. Generic, no examples, poor structure.
- 0-1  = No useful content.

Return ONLY a valid JSON object. No markdown, no explanation, no preamble.

Required format:
{
  "clarity": <int 0-10>,
  "relevance": <int 0-10>,
  "star_quality": <int 0-10>,
  "specificity": <int 0-10>,
  "communication": <int 0-10>,
  "job_fit": <int 0-10>,
  "summary": "<2 sentence recruiter note>",
  "star_detected": <true|false>,
  "key_strength": "<single most impressive thing>",
  "key_improvement": "<single most important improvement>",
  "recruiter_verdict": "<Strong Advance|Advance|Borderline|Do Not Advance>",
  "star_components": {
    "situation": <true|false>,
    "task": <true|false>,
    "action": <true|false>,
    "result": <true|false>
  }
}"""


# ── Question classifier ───────────────────────────────────────────────────

def classify_question(question: str) -> str:
    """
    Classify the question type so scoring weights can be adjusted.
    Returns: "introduction" | "behavioural" | "technical" | "fit" | "general"
    """
    q = question.lower()

    intro_patterns = [
        r"\btell me about yourself\b",
        r"\bintroduce yourself\b",
        r"\bwalk me through your (background|resume|experience)\b",
        r"\bwho are you\b",
    ]
    if any(re.search(p, q) for p in intro_patterns):
        return "introduction"

    behavioural_patterns = [
        r"\btell me about a time\b",
        r"\bdescribe a (situation|time|experience)\b",
        r"\bgive me an example\b",
        r"\bhow (did you|have you) (handle|deal|manage|overcome|resolve)\b",
        r"\bwhat (did you|would you) do when\b",
        r"\bchallenge you faced\b",
        r"\bconflict\b",
        r"\bteamwork\b",
        r"\bpressure\b",
        r"\bfailure\b",
    ]
    if any(re.search(p, q) for p in behavioural_patterns):
        return "behavioural"

    fit_patterns = [
        r"\bwhy (do you want|are you interested in|this (role|company|position))\b",
        r"\bwhat (motivates|interests|excites) you\b",
        r"\bwhere do you see yourself\b",
        r"\bwhy should we hire\b",
        r"\bstrong fit\b",
        r"\bwhat can you bring\b",
    ]
    if any(re.search(p, q) for p in fit_patterns):
        return "fit"

    technical_patterns = [
        r"\bhow (does|do|would you implement|works)\b",
        r"\bexplain\b",
        r"\bdifference between\b",
        r"\bdesign\b",
        r"\barchitect\b",
        r"\boptimi[sz]e\b",
        r"\bdebug\b",
        r"\bscale\b",
        r"\bperformance\b",
    ]
    if any(re.search(p, q) for p in technical_patterns):
        return "technical"

    return "general"


# ── Prompt builder ────────────────────────────────────────────────────────

def build_prompt(question: str, answer: str, jd_text: str = "") -> str:
    """
    Build the user-turn prompt for the scoring LLM.

    Parameters
    ----------
    question : str  — The interview question asked
    answer   : str  — The candidate's transcribed answer
    jd_text  : str  — Optional job description (enables job_fit scoring)
    """
    q_type = classify_question(question)

    # Per-type guidance injected into the prompt
    type_guidance = {
        "introduction": (
            "This is an introduction/background question. "
            "Be lenient on STAR structure — a clear narrative about their background is fine. "
            "Focus on clarity, communication, and whether they convey relevant experience."
        ),
        "behavioural": (
            "This is a behavioural question. "
            "STAR structure (Situation, Task, Action, Result) is expected. "
            "Penalise vague answers without specific examples. "
            "Reward answers with measurable outcomes and clear personal ownership."
        ),
        "technical": (
            "This is a technical question. "
            "Evaluate depth of knowledge — do they know the 'why' not just the 'what'? "
            "Reward specific technical details, correct terminology, and practical experience. "
            "STAR structure is less important here."
        ),
        "fit": (
            "This is a motivation/fit question. "
            "Focus heavily on job_fit — does their answer show genuine research into the role? "
            "Do they connect their background to the specific role requirements? "
            "Generic answers ('I want to grow') should score low on job_fit."
        ),
        "general": (
            "Score this answer as a general interview response. "
            "Apply balanced weights across all dimensions."
        ),
    }

    guidance = type_guidance.get(q_type, type_guidance["general"])

    # JD section (appended only when JD text is present)
    jd_section = ""
    if jd_text and jd_text.strip():
        jd_section = f"""
JOB DESCRIPTION (use this to score job_fit):
{jd_text.strip()[:1500]}
"""

    prompt = f"""Question type: {q_type.upper()}
Scoring guidance: {guidance}
{jd_section}
INTERVIEW QUESTION:
{question}

CANDIDATE'S ANSWER (Whisper transcription — minor artifacts are expected):
{answer}

Score this answer and return the JSON object as specified in the system prompt."""

    return prompt