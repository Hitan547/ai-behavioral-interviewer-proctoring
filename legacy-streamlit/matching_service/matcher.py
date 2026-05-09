"""
matching_service/matcher.py
---------------------------
Scores resumes against a Job Description using Groq LLM.

Functions:
    score_resume_vs_jd(resume_text, jd_text)  → single result dict
    score_all_resumes(resumes, jd_text)        → sorted list of result dicts

Usage:
    from matching_service.matcher import score_all_resumes
"""

import os
import json
import time
import re
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
_ENV_PATH = _HERE.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
else:
    load_dotenv()

_api_key = (os.getenv("GROQ_API_KEY") or "").strip()
if not _api_key and _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=True)
    _api_key = (os.getenv("GROQ_API_KEY") or "").strip()

if not _api_key:
    raise EnvironmentError("GROQ_API_KEY is not set. Add it in project .env")

# Use GROQ_API_KEY (same as answer_service)
client = Groq(api_key=_api_key)

MODEL    = "llama-3.1-8b-instant"
TEMP     = 0.2
RATE_DELAY = 0.6   # seconds between calls — avoids Groq rate limit
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _groq_json_completion(messages: list, max_tokens: int, retries: int = 2):
    """Call Groq with JSON mode and a small retry budget for transient failures."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            return client.chat.completions.create(
                model=MODEL,
                temperature=TEMP,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(0.8)
    raise last_error


# ── Prompts ───────────────────────────────────────────────────────────────

MATCH_SYSTEM = """You are a professional recruiter AI. 
You compare a candidate's resume against a job description and return a JSON score.
You must return ONLY valid JSON. No markdown, no backticks, no explanation outside JSON."""

MATCH_PROMPT = """Compare this resume against the job description below.

JOB DESCRIPTION:
{jd_text}

RESUME:
{resume_text}

Return ONLY this JSON (no markdown, no extra text):
{{
  "match_score": <float between 0.0 and 10.0>,
  "match_reason": "<2-3 sentence summary of why this candidate does or does not fit>",
  "key_matches": ["<skill or experience that matches>", "..."],
  "key_gaps": ["<missing skill or requirement>", "..."]
}}

Scoring guide:
9-10 = Exceptional fit, meets almost all requirements
7-8  = Strong fit, meets most requirements
5-6  = Moderate fit, meets some requirements
3-4  = Weak fit, significant gaps
0-2  = Poor fit, does not meet requirements"""


EXTRACT_SYSTEM = """You are a resume parser. Extract candidate info and return ONLY valid JSON."""

EXTRACT_PROMPT = """From this resume text, extract the candidate's full name and email address.

RESUME:
{resume_text}

Return ONLY this JSON (no markdown, no extra text):
{{
  "name": "<full name or 'Unknown' if not found>",
  "email": "<email@example.com or 'unknown@email.com' if not found>"
}}"""


# ── Private helpers ───────────────────────────────────────────────────────

def _safe_parse(text: str) -> dict:
    """Parse LLM response to JSON safely. Strips markdown fences if present."""
    try:
        # Strip markdown code fences if LLM adds them anyway
        cleaned = re.sub(r"```(?:json)?", "", text).strip()
        cleaned = cleaned.strip("`").strip()
        return json.loads(cleaned)
    except Exception:
        # Fallback: extract first JSON object from mixed text responses.
        try:
            cleaned = re.sub(r"```(?:json)?", "", text or "").strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(cleaned[start : end + 1])
        except Exception:
            pass
        return {}


def _extract_email_regex(resume_text: str) -> str:
    """Extract first valid-looking email from plain text."""
    m = EMAIL_REGEX.search(resume_text or "")
    return m.group(0).strip() if m else ""


def _extract_name_regex(resume_text: str) -> str:
    """Best-effort name extraction from top resume lines when LLM fails."""
    lines = [ln.strip() for ln in (resume_text or "").splitlines() if ln.strip()]
    for ln in lines[:20]:
        lower = ln.lower()
        if "@" in ln:
            continue
        if any(tok in lower for tok in ["resume", "curriculum", "summary", "objective", "education"]):
            continue
        if len(ln) > 60:
            continue

        words = [w for w in re.split(r"\s+", ln) if w]
        alpha_words = [w for w in words if re.match(r"^[A-Za-z][A-Za-z'\-.]*$", w)]
        if len(alpha_words) >= 2:
            return " ".join(alpha_words[:4]).strip()
    return ""


def _extract_candidate_info(resume_text: str) -> dict:
    """Extract name and email from resume using LLM."""
    fallback_email = _extract_email_regex(resume_text)
    fallback_name = _extract_name_regex(resume_text)

    try:
        response = _groq_json_completion(
            max_tokens=200,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user",   "content": EXTRACT_PROMPT.format(
                    resume_text=resume_text[:2000]  # first 2000 chars is enough
                )},
            ],
        )
        result = _safe_parse(response.choices[0].message.content)
        name = (result.get("name") or "").strip()
        email = (result.get("email") or "").strip()

        if not email or email.lower().startswith("unknown@"):
            email = fallback_email or "unknown@email.com"
        if not name or name.lower() == "unknown":
            name = fallback_name or "Unknown"

        return {
            "name":  name,
            "email": email,
        }
    except Exception:
        return {
            "name": fallback_name or "Unknown",
            "email": fallback_email or "unknown@email.com",
        }


# ── Public functions ──────────────────────────────────────────────────────

def score_resume_vs_jd(resume_text: str, jd_text: str) -> dict:
    """
    Score a single resume against a JD.

    Returns:
        {
            match_score:   float (0-10),
            match_reason:  str,
            key_matches:   list[str],
            key_gaps:      list[str],
            name:          str,
            email:         str,
        }
    """
    fallback = {
        "match_score":  5.0,
        "match_reason": "Could not parse LLM response.",
        "key_matches":  [],
        "key_gaps":     [],
        "name":         "Unknown",
        "email":        "unknown@email.com",
    }

    try:
        # Step 1: Score the resume vs JD
        response = _groq_json_completion(
            max_tokens=600,
            messages=[
                {"role": "system", "content": MATCH_SYSTEM},
                {"role": "user",   "content": MATCH_PROMPT.format(
                    jd_text=jd_text[:3000],
                    resume_text=resume_text[:3000],
                )},
            ],
        )

        raw = response.choices[0].message.content
        parsed = _safe_parse(raw)

        if not parsed or "match_score" not in parsed:
            info = _extract_candidate_info(resume_text)
            return {
                **fallback,
                "name": info.get("name", "Unknown"),
                "email": info.get("email", "unknown@email.com"),
                "match_reason": "LLM parse failed. Check GROQ key/quota or resume text quality.",
            }

        # Step 2: Extract name + email
        info = _extract_candidate_info(resume_text)

        return {
            "match_score":  round(float(parsed.get("match_score", 5.0)), 1),
            "match_reason": parsed.get("match_reason", ""),
            "key_matches":  parsed.get("key_matches", []),
            "key_gaps":     parsed.get("key_gaps",    []),
            "name":         info["name"],
            "email":        info["email"],
        }

    except Exception as e:
        print(f"[matcher] score_resume_vs_jd error: {e}")
        return {
            **fallback,
            "match_reason": f"LLM call failed: {str(e)[:140]}",
        }


def score_all_resumes(resumes: list[dict], jd_text: str) -> list[dict]:
    """
    Score a list of resumes against a JD.

    Input:
        resumes  — list of dicts: [{filename: str, text: str}, ...]
        jd_text  — full JD text string

    Returns:
        list of dicts sorted by match_score descending:
        [{
            filename:     str,
            match_score:  float,
            match_reason: str,
            key_matches:  list,
            key_gaps:     list,
            name:         str,
            email:        str,
        }, ...]
    """
    results = []

    for i, resume in enumerate(resumes):
        filename    = resume.get("filename", f"resume_{i+1}.pdf")
        resume_text = resume.get("text", "")

        print(f"[matcher] Scoring {i+1}/{len(resumes)}: {filename}")

        if not resume_text.strip():
            results.append({
                "filename":     filename,
                "match_score":  0.0,
                "match_reason": "Resume text could not be extracted.",
                "key_matches":  [],
                "key_gaps":     ["Resume unreadable"],
                "name":         filename.replace(".pdf", ""),
                "email":        "unknown@email.com",
            })
            continue

        result = score_resume_vs_jd(resume_text, jd_text)
        result["filename"] = filename
        results.append(result)

        # Rate limit protection — pause between calls
        if i < len(resumes) - 1:
            time.sleep(RATE_DELAY)

    # Sort by match_score highest first
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results