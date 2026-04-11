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
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Use GROQ_API_KEY (same as answer_service)
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL    = "llama-3.1-8b-instant"
TEMP     = 0.2
RATE_DELAY = 0.6   # seconds between calls — avoids Groq rate limit


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
        return {}


def _extract_candidate_info(resume_text: str) -> dict:
    """Extract name and email from resume using LLM."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=TEMP,
            max_tokens=200,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user",   "content": EXTRACT_PROMPT.format(
                    resume_text=resume_text[:2000]  # first 2000 chars is enough
                )},
            ],
        )
        result = _safe_parse(response.choices[0].message.content)
        return {
            "name":  result.get("name",  "Unknown"),
            "email": result.get("email", "unknown@email.com"),
        }
    except Exception:
        return {"name": "Unknown", "email": "unknown@email.com"}


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
        response = client.chat.completions.create(
            model=MODEL,
            temperature=TEMP,
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
            return fallback

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
        return fallback


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