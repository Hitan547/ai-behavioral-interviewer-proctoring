"""
resume_parser.py
----------------
Key fixes:
- load_dotenv() uses explicit absolute path so it works regardless of
  which directory Streamlit is launched from (the most common cause of
  GROQ_API_KEY being empty even when .env exists)
- Every step prints to terminal so you can see exactly where it fails
- Added pymupdf fallback for image-heavy PDFs
- Minimum text length check before calling LLM
"""

import os
import re
import json
from dotenv import load_dotenv

# Use absolute path — works no matter where `streamlit run` is called from
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_HERE, ".env"), override=True)

_client = None  # Lazy Groq client — created on first use


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY_2", "").strip()
        if not key:
            print("[resume_parser] ❌ GROQ_API_KEY not set. Check .env in project root.", flush=True)
            raise EnvironmentError("GROQ_API_KEY missing")
        print(f"[resume_parser] ✅ API key loaded: {key[:12]}...", flush=True)
        from groq import Groq
        _client = Groq(api_key=key)
    return _client


# ── PDF extraction ────────────────────────────────────────────────────────

def extract_resume_text(pdf_path: str) -> str:
    return _extract_pdf_text(pdf_path)


def extract_jd_text(pdf_path: str) -> str:
    return _extract_pdf_text(pdf_path)


def _extract_pdf_text(pdf_path: str) -> str:
    text = ""

    # Primary: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            text += page.extract_text() or ""
        text = text.strip()
    except Exception as e:
        print(f"[resume_parser] PyPDF2 error: {e}", flush=True)

    # Fallback: pymupdf (better for complex PDFs)
    if len(text) < 100:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            fitz_text = "".join(page.get_text() for page in doc)
            doc.close()
            if len(fitz_text.strip()) > len(text):
                text = fitz_text.strip()
                print(f"[resume_parser] pymupdf used — {len(text)} chars", flush=True)
        except ImportError:
            pass
        except Exception as e:
            print(f"[resume_parser] pymupdf error: {e}", flush=True)

    print(f"[resume_parser] PDF extracted: {len(text)} chars from {os.path.basename(pdf_path)}", flush=True)
    if len(text) < 50:
        print("[resume_parser] ⚠️  Very little text — PDF may be image-based (scanned)", flush=True)
    return text


# ── Question generation ────────────────────────────────────────────────────

def generate_questions(resume_text: str, jd_text: str = "") -> list:
    resume_text = (resume_text or "").strip()
    jd_text     = (jd_text or "").strip()

    if not resume_text:
        print("[resume_parser] ⚠️  No resume text — returning defaults", flush=True)
        return _default_questions()

    print(f"[resume_parser] Generating: resume={len(resume_text)}c, jd={len(jd_text)}c", flush=True)

    if jd_text:
        return _generate_with_jd(resume_text, jd_text)
    return _generate_from_resume(resume_text)


def _generate_from_resume(resume_text: str) -> list:
    prompt = f"""You are a senior technical interviewer.

Here is the candidate's resume:
{resume_text[:3000]}

Generate exactly 5 interview questions based specifically on THIS resume.

Rules:
- 2 questions about specific projects or work mentioned in the resume
- 2 questions about specific skills or technologies listed in the resume
- 1 behavioral question (teamwork, challenge, leadership)
- Questions MUST reference actual details from this resume
- Do NOT ask "tell me about yourself" or "walk me through a project end-to-end"

Return ONLY a JSON array of 5 strings. No markdown, no explanation.
["Question 1?", "Question 2?", "Question 3?", "Question 4?", "Question 5?"]"""

    return _call_llm(prompt)


def _generate_with_jd(resume_text: str, jd_text: str) -> list:
    prompt = f"""You are a senior recruiter screening a candidate for a specific role.

=== JOB DESCRIPTION ===
{jd_text[:2000]}

=== CANDIDATE RESUME ===
{resume_text[:2000]}

Generate exactly 5 interview questions for THIS candidate for THIS role.
- 2 questions mapping candidate experience to JD requirements
- 1 question on a visible gap between JD and resume
- 1 behavioral question from JD responsibilities
- 1 motivation/fit question for this specific role

Return ONLY a JSON array of 5 strings. No markdown, no explanation.
["Question 1?", "Question 2?", "Question 3?", "Question 4?", "Question 5?"]"""

    return _call_llm(prompt)


def _call_llm(prompt: str) -> list:
    print("[resume_parser] Calling LLM...", flush=True)
    try:
        client   = _get_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=700,
        )
        raw = response.choices[0].message.content.strip()
        print(f"[resume_parser] LLM replied ({len(raw)} chars): {raw[:150]!r}", flush=True)

        raw = re.sub(r"```json|```", "", raw).strip()

        # Pull out the JSON array even if model adds surrounding text
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            raw = match.group(0)

        questions = json.loads(raw)

        if isinstance(questions, list) and len(questions) >= 5:
            print(f"[resume_parser] ✅ {len(questions)} custom questions generated", flush=True)
            return [str(q) for q in questions[:5]]

        print(f"[resume_parser] ⚠️  Got {len(questions)} questions (need 5) — using defaults", flush=True)
        return _default_questions()

    except EnvironmentError:
        return _default_questions()
    except json.JSONDecodeError as e:
        print(f"[resume_parser] ❌ JSON parse error: {e} | raw={raw!r}", flush=True)
        return _default_questions()
    except Exception as e:
        print(f"[resume_parser] ❌ LLM failed: {type(e).__name__}: {e}", flush=True)
        return _default_questions()


def _default_questions() -> list:
    print("[resume_parser] ⚠️  USING FALLBACK QUESTIONS", flush=True)
    return [
        "Walk me through a project you built end-to-end — what was your role and what did you deliver?",
        "Tell me about a time you had to learn a new technology quickly under pressure.",
        "Describe a situation where you disagreed with a technical decision made by your team.",
        "What's the most complex problem you've solved — how did you approach it?",
        "Why are you interested in this role, and what specifically makes you a strong fit?",
    ]