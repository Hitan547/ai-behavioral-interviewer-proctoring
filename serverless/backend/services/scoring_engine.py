"""Serverless scoring engine with real LLM scoring via Groq API.

Ports the LLM-based scoring from the Streamlit version (answer_service/llm_engine.py)
to work in Lambda using only stdlib (urllib.request) — no groq SDK needed.
Falls back to heuristic scoring if the Groq API is unreachable.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


# ── LLM Scoring (primary) ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior technical recruiter with 10+ years of experience screening candidates for software engineering, data science, and AI/ML roles.

You are evaluating a candidate's interview answer. The answer may have been transcribed by speech-to-text and could contain minor artifacts. Do NOT penalise transcription artifacts — evaluate the underlying substance.

COHERENCE CHECK (CRITICAL — do this FIRST):
Before scoring, assess whether the answer is coherent and intelligible.
If the text contains mostly nonsensical phrases or random word combinations,
set ALL dimension scores to 2 or below and note "Transcript appears corrupted".

Score the answer on exactly these 6 dimensions, each from 0 to 10:

1. clarity        — Is the answer easy to follow? Clear structure, logical flow.
2. relevance      — Does it directly address what was asked?
3. star_quality   — Does it follow Situation→Task→Action→Result structure?
4. specificity    — Are there concrete examples, numbers, technologies, outcomes?
5. communication  — Confidence, vocabulary, professional tone.
6. job_fit        — Does the answer show alignment with the role/JD requirements?

CALIBRATION:
- 8-10 = Would strongly advance. Specific, structured, impressive.
- 6-7  = Would advance. Solid answer with minor gaps.
- 4-5  = Borderline. Some substance but vague or incomplete.
- 2-3  = Weak. Generic, no examples, poor structure.
- 0-1  = No useful content.

Return ONLY a valid JSON object. No markdown, no explanation.

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
  "recruiter_verdict": "<Strong Advance|Advance|Borderline|Do Not Advance>"
}"""


def _classify_question(question: str) -> str:
    """Classify question type for scoring guidance."""
    q = question.lower()
    if any(p in q for p in ["tell me about yourself", "introduce yourself", "walk me through"]):
        return "introduction"
    if any(p in q for p in ["tell me about a time", "describe a situation", "give me an example", "challenge you faced"]):
        return "behavioural"
    if any(p in q for p in ["why do you want", "why are you interested", "where do you see yourself", "why should we"]):
        return "fit"
    if any(p in q for p in ["how does", "explain", "difference between", "design", "optimize", "debug", "scale"]):
        return "technical"
    return "general"


_TYPE_GUIDANCE = {
    "introduction": "This is an introduction question. Be lenient on STAR structure. Focus on clarity and communication.",
    "behavioural": "This is a behavioural question. STAR structure is expected. Penalise vague answers without specific examples.",
    "technical": "This is a technical question. Evaluate depth of knowledge. STAR structure is less important.",
    "fit": "This is a motivation/fit question. Focus on job_fit — does the answer show genuine interest?",
    "general": "Score this as a general interview response with balanced weights.",
}


def _build_user_prompt(question: str, answer: str, jd_text: str) -> str:
    q_type = _classify_question(question)
    guidance = _TYPE_GUIDANCE.get(q_type, _TYPE_GUIDANCE["general"])
    jd_section = f"\nJOB DESCRIPTION:\n{jd_text.strip()[:1500]}\n" if jd_text.strip() else ""
    return (
        f"Question type: {q_type.upper()}\n"
        f"Scoring guidance: {guidance}\n"
        f"{jd_section}\n"
        f"INTERVIEW QUESTION:\n{question}\n\n"
        f"CANDIDATE'S ANSWER:\n{answer}\n\n"
        f"Score this answer and return the JSON object as specified in the system prompt."
    )


def _get_groq_api_key() -> str:
    """Resolve Groq API key from env or SSM Parameter Store."""
    env_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY_2")
    if env_key:
        return env_key.strip()
    parameter_name = os.environ.get("GROQ_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return ""
    try:
        import boto3
        response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
        return str(response.get("Parameter", {}).get("Value", "")).strip()
    except Exception:
        return ""


def _call_groq_scoring(question: str, answer: str, jd_text: str) -> dict[str, Any] | None:
    """Call Groq LLM to score an answer. Returns parsed dict or None on failure."""
    api_key = _get_groq_api_key()
    if not api_key:
        return None

    user_prompt = _build_user_prompt(question, answer, jd_text)
    body = json.dumps({
        "model": os.environ.get("SCORING_MODEL", "llama-3.1-8b-instant"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
    }).encode("utf-8")

    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        raw = str(data["choices"][0]["message"]["content"])
        cleaned = re.sub(r"```json|```", "", raw).strip()
        scores = json.loads(cleaned)
        return _validate_llm_scores(scores)
    except Exception:
        return None


def _validate_llm_scores(scores: dict[str, Any]) -> dict[str, Any]:
    """Ensure all expected keys exist with proper types."""
    int_keys = ["clarity", "relevance", "star_quality", "specificity", "communication", "job_fit"]
    for k in int_keys:
        if k not in scores or not isinstance(scores[k], (int, float)):
            scores[k] = 0
        else:
            scores[k] = max(0, min(10, int(scores[k])))
    scores.setdefault("summary", "")
    scores.setdefault("star_detected", False)
    scores.setdefault("key_strength", "N/A")
    scores.setdefault("key_improvement", "N/A")
    scores.setdefault("recruiter_verdict", "Borderline")
    return scores


def _llm_score_to_100(scores: dict[str, Any]) -> int:
    """Convert 6 LLM dimension scores (0-10 each) to a single 0-100 score."""
    weights = {
        "clarity": 0.15,
        "relevance": 0.20,
        "star_quality": 0.15,
        "specificity": 0.20,
        "communication": 0.15,
        "job_fit": 0.15,
    }
    total = sum(scores.get(k, 0) * w for k, w in weights.items())
    return round(total * 10)


# ── Heuristic Scoring (fallback) ─────────────────────────────────────────

def _heuristic_score_answer(answer: str, question: str, jd_text: str) -> dict[str, Any]:
    """Fallback scoring when LLM is unavailable. Uses word count + keyword matching."""
    word_count = len(answer.split())
    question_terms = _terms(question)
    jd_terms = _terms(jd_text)
    answer_terms = _terms(answer)
    relevance_hits = len((question_terms | jd_terms) & answer_terms)

    length_score = min(35, word_count * 2)
    relevance_score = min(35, relevance_hits * 7)
    structure_score = _structure_score(answer)
    score = max(25, min(100, length_score + relevance_score + structure_score))

    return {
        "score": score,
        "summary": f"Heuristic: {word_count} words, {relevance_hits} keyword matches.",
        "method": "heuristic",
    }


def _structure_score(answer: str) -> int:
    lowered = answer.lower()
    markers = ["situation", "task", "action", "result", "because", "therefore", "impact", "measured"]
    return min(30, 8 + sum(4 for marker in markers if marker in lowered))


def _terms(text: str) -> set[str]:
    return {
        word.strip(".,:;!?()[]{}").lower()
        for word in str(text or "").split()
        if len(word.strip(".,:;!?()[]{}")) >= 4
    }


# ── Main Scoring Function ────────────────────────────────────────────────

def score_interview(
    *,
    job: dict[str, Any],
    candidate: dict[str, Any],
    submission: dict[str, Any],
) -> dict[str, Any]:
    """Score a complete interview submission using LLM (with heuristic fallback)."""
    questions = candidate.get("questions") or []
    answers = submission.get("answers") or []
    answers_by_index = {
        int(answer.get("questionIndex", -1)): answer
        for answer in answers
        if isinstance(answer, dict)
    }
    jd_text = str(job.get("jdText", ""))

    per_question = []
    for index, question in enumerate(questions):
        answer_data = answers_by_index.get(index, {})
        answer_text = str(answer_data.get("answerText", "")).strip()
        per_question.append(_score_single_answer(index, str(question), answer_text, jd_text))

    answered_scores = [item["score"] for item in per_question if item["answered"]]
    base_score = round(sum(answered_scores) / len(answered_scores)) if answered_scores else 0
    integrity_risk = summarize_integrity_risk(submission.get("integritySignals", {}))
    penalty = integrity_risk["scorePenalty"]
    final_score = max(0, min(100, base_score - penalty))
    recommendation = _recommendation(final_score, integrity_risk["level"])

    return {
        "finalScore": final_score,
        "recommendation": recommendation,
        "integrityRisk": integrity_risk,
        "perQuestion": per_question,
        "summary": _summary(candidate, final_score, recommendation, integrity_risk),
    }


def _score_single_answer(index: int, question: str, answer: str, jd_text: str) -> dict[str, Any]:
    """Score one answer using LLM, falling back to heuristic if LLM fails."""
    if not answer:
        return {
            "questionIndex": index,
            "question": question,
            "answered": False,
            "score": 0,
            "verdict": "Missing",
            "summary": "No answer submitted.",
            "method": "none",
        }

    # Try LLM scoring first
    llm_result = _call_groq_scoring(question, answer, jd_text)

    if llm_result:
        score = _llm_score_to_100(llm_result)
        verdict = llm_result.get("recruiter_verdict", "Borderline")
        # Map LLM verdict to our format
        if verdict in ("Strong Advance", "Advance"):
            simple_verdict = "Strong"
        elif verdict == "Borderline":
            simple_verdict = "Needs Review"
        else:
            simple_verdict = "Weak"

        return {
            "questionIndex": index,
            "question": question,
            "answered": True,
            "score": score,
            "verdict": simple_verdict,
            "summary": llm_result.get("summary", ""),
            "method": "llm",
            "dimensions": {
                "clarity": llm_result.get("clarity", 0),
                "relevance": llm_result.get("relevance", 0),
                "starQuality": llm_result.get("star_quality", 0),
                "specificity": llm_result.get("specificity", 0),
                "communication": llm_result.get("communication", 0),
                "jobFit": llm_result.get("job_fit", 0),
            },
            "keyStrength": llm_result.get("key_strength", "N/A"),
            "keyImprovement": llm_result.get("key_improvement", "N/A"),
            "recruiterVerdict": llm_result.get("recruiter_verdict", "Borderline"),
            "starDetected": llm_result.get("star_detected", False),
        }

    # Fallback to heuristic
    heuristic = _heuristic_score_answer(answer, question, jd_text)
    score = heuristic["score"]
    if score >= 75:
        verdict = "Strong"
    elif score >= 55:
        verdict = "Needs Review"
    else:
        verdict = "Weak"

    return {
        "questionIndex": index,
        "question": question,
        "answered": True,
        "score": score,
        "verdict": verdict,
        "summary": heuristic["summary"],
        "method": "heuristic",
    }


# ── Integrity Risk ────────────────────────────────────────────────────────

def summarize_integrity_risk(signals: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(signals, dict):
        signals = {}
    tab_switches = _non_negative_int(signals.get("tabSwitches", 0))
    fullscreen_exits = _non_negative_int(signals.get("fullscreenExits", 0))
    copy_paste_attempts = _non_negative_int(signals.get("copyPasteAttempts", 0))
    devtools_attempts = _non_negative_int(signals.get("devtoolsAttempts", 0))
    face_not_detected = _non_negative_int(signals.get("faceNotDetected", 0))
    multiple_faces = _non_negative_int(signals.get("multipleFaces", 0))

    raw_risk = (
        tab_switches * 2
        + fullscreen_exits * 3
        + copy_paste_attempts * 4
        + devtools_attempts * 5
        + face_not_detected * 2
        + multiple_faces * 5
    )
    if raw_risk >= 12:
        level = "High"
        penalty = 10
    elif raw_risk >= 5:
        level = "Medium"
        penalty = 5
    else:
        level = "Low"
        penalty = 0

    return {
        "level": level,
        "scorePenalty": penalty,
        "tabSwitches": tab_switches,
        "fullscreenExits": fullscreen_exits,
        "copyPasteAttempts": copy_paste_attempts,
        "devtoolsAttempts": devtools_attempts,
        "faceNotDetected": face_not_detected,
        "multipleFaces": multiple_faces,
        "eventCount": len(signals.get("events", [])) if isinstance(signals.get("events"), list) else 0,
    }


# ── Helpers ───────────────────────────────────────────────────────────────

def _recommendation(score: int, risk_level: str) -> str:
    if score >= 75 and risk_level != "High":
        return "Strong Fit"
    if score < 50 or risk_level == "High":
        return "Not Recommended"
    return "Needs Review"


def _summary(candidate: dict[str, Any], score: int, recommendation: str, integrity_risk: dict[str, Any]) -> str:
    name = candidate.get("name") or "Candidate"
    return (
        f"{name} scored {score}/100 with a {recommendation} recommendation. "
        f"Integrity risk is {integrity_risk['level']}."
    )


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)
