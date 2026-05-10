"""
answer_service/llm_engine.py
-----------------------------
Calls Groq / LLaMA to score interview answers.
"""

import os
import re
import json
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv
from answer_service.prompt import SYSTEM_PROMPT, build_prompt

_HERE = Path(__file__).resolve().parent
_ENV_PATH = _HERE.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
else:
    load_dotenv()

_api_key = (os.environ.get("GROQ_API_KEY_2") or os.environ.get("GROQ_API_KEY") or "").strip()
if not _api_key and _ENV_PATH.exists():
    # Recover from inherited blank environment variables.
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    _api_key = (os.environ.get("GROQ_API_KEY_2") or os.environ.get("GROQ_API_KEY") or "").strip()

if not _api_key:
    raise EnvironmentError(
        "\n\n❌  GROQ_API_KEY is not set.\n"
        "    Add it to your .env file:\n"
        "        GROQ_API_KEY=gsk_...\n"
        "    Then restart the answer service.\n"
    )

client = Groq(api_key=_api_key)


def evaluate_answer(question: str, answer: str, jd_text: str = "") -> dict:
    """
    Send question + answer (+ optional JD) to LLaMA and return dimension scores.

    Returns a dict with keys: clarity, relevance, star_quality, specificity,
    communication, job_fit, summary, star_detected, key_strength,
    key_improvement, recruiter_verdict, star_components.

    On any failure returns a safe fallback dict so the API never 500s.
    """
    if not answer or not answer.strip():
        return _empty_scores("No answer provided.")

    user_prompt = build_prompt(question, answer, jd_text=jd_text)
    output_text = ""  # defined here so it's always in scope for error logging

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        output_text = response.choices[0].message.content.strip()

        # Strip markdown fences if the model adds them
        output_text = re.sub(r"```json|```", "", output_text).strip()

        scores = json.loads(output_text)

        # Validate required keys are present; fill missing ones safely
        scores = _validate_and_fill(scores)
        return scores

    except json.JSONDecodeError as e:
        print(f"[llm_engine] JSON parse error: {e}\nRaw output: {output_text!r}")
        return _empty_scores("LLM returned non-JSON output.")

    except Exception as e:
        print(f"[llm_engine] Groq API error: {e}")
        return _empty_scores(f"Groq error: {e}")


def _validate_and_fill(scores: dict) -> dict:
    """Ensure all expected keys exist so downstream code never KeyErrors."""
    int_keys = ["clarity", "relevance", "star_quality", "specificity", "communication", "job_fit"]
    for k in int_keys:
        if k not in scores or not isinstance(scores[k], (int, float)):
            scores[k] = 0

    scores.setdefault("summary", "")
    scores.setdefault("star_detected", False)
    scores.setdefault("key_strength", "N/A")
    scores.setdefault("key_improvement", "N/A")
    scores.setdefault("recruiter_verdict", "Borderline")
    scores.setdefault("star_components", {
        "situation": False, "task": False, "action": False, "result": False
    })
    return scores


def _empty_scores(reason: str) -> dict:
    """Safe fallback — all dimensions 0, reason in summary."""
    return {
        "clarity":         0,
        "relevance":       0,
        "star_quality":    0,
        "specificity":     0,
        "communication":   0,
        "job_fit":         0,
        "summary":         reason,
        "star_detected":   False,
        "key_strength":    "N/A",
        "key_improvement": "Provide a complete answer",
        "recruiter_verdict": "Do Not Advance",
        "star_components": {
            "situation": False, "task": False, "action": False, "result": False
        },
    }