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
from typing import Any
from dotenv import load_dotenv

# Use absolute path — works no matter where `streamlit run` is called from
_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_HERE, ".env"), override=True)

_client = None  # Lazy Groq client — created on first use
_DOMAIN_CHOICES = {
    "machine_learning",
    "software_engineering",
    "data_engineering",
    "finance",
    "marketing",
    "product_management",
    "healthcare",
    "legal",
    "hr",
    "general",
}


def _get_client():
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY_2", "").strip()
        if not key:
            print("[resume_parser] ERROR GROQ_API_KEY not set. Check .env in project root.", flush=True)
            raise EnvironmentError("GROQ_API_KEY missing")
        print("[resume_parser] OK GROQ client initialized", flush=True)
        from groq import Groq
        _client = Groq(api_key=key)
    return _client


def _extract_json_payload(raw: str) -> dict:
    cleaned = re.sub(r"```json|```", "", (raw or "")).strip()
    if not cleaned:
        return {}

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    return {}


def _normalize_domain(value: Any) -> str:
    domain = re.sub(r"[^a-z_\s-]", "", str(value or "").strip().lower())
    domain = domain.replace("-", "_")
    domain = re.sub(r"\s+", "_", domain)
    return domain if domain in _DOMAIN_CHOICES else "general"


def _normalize_term_list(value: Any, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []

    seen = set()
    out = []
    for item in value:
        term = re.sub(r"\s+", " ", str(item or "").strip())
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
        if len(out) >= max_items:
            break
    return out


def _normalize_vocab_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    domain = _normalize_domain(payload.get("domain"))
    sub_domain = re.sub(r"\s+", " ", str(payload.get("sub_domain") or "").strip())[:80]

    acronyms = _normalize_term_list(payload.get("acronyms"), max_items=50)
    proper_nouns = _normalize_term_list(payload.get("proper_nouns"), max_items=50)
    terms = _normalize_term_list(payload.get("terms"), max_items=80)

    # Keep a compact, useful terms list by removing items already listed elsewhere.
    reserved = {x.casefold() for x in acronyms + proper_nouns}
    compact_terms = [t for t in terms if t.casefold() not in reserved][:50]

    return {
        "domain": domain,
        "sub_domain": sub_domain,
        "terms": compact_terms,
        "acronyms": acronyms,
        "proper_nouns": proper_nouns,
    }


def extract_vocab_from_resume(resume_text: str, jd_text: str = "") -> dict:
    """
    Extract domain and technical vocabulary from resume + optional JD.

    Returns:
        {
            "domain": str,
            "sub_domain": str,
            "terms": list[str],
            "acronyms": list[str],
            "proper_nouns": list[str],
        }
    """
    resume_text = (resume_text or "").strip()
    jd_text = (jd_text or "").strip()

    fallback = {
        "domain": "general",
        "sub_domain": "",
        "terms": [],
        "acronyms": [],
        "proper_nouns": [],
    }

    if not resume_text:
        return fallback

    jd_block = f"\nJob Description:\n{jd_text[:1000]}\n" if jd_text else ""
    prompt = f"""You are preparing a speech-to-text system to transcribe a technical interview.

The candidate will SPEAK their answers aloud. Your job is to find every word or phrase
that a speech-to-text model would likely mishear or confuse.

Resume:
{resume_text[:3000]}
{jd_block}

Return ONLY a JSON object:
{{
    "domain": "one of: machine_learning, software_engineering, data_engineering, finance, marketing, product_management, healthcare, legal, hr, general",
    "sub_domain": "specific sub-field e.g. NLP, RAG, quantitative_finance",
    "acronyms": [
        "every acronym the candidate might say: FAISS, BM25, RAG, RRF, RLHF, LoRA, etc.",
        "include ALL uppercase abbreviations from the resume"
    ],
    "proper_nouns": [
        "every tool/library/framework/company name: LangChain, LlamaIndex, Pinecone, Weaviate, etc.",
        "include version names, model names like GPT-4, LLaMA, Whisper, DistilBERT"
    ],
    "terms": [
        "compound technical phrases that get mangled: reciprocal rank fusion, dense retrieval, sparse retrieval",
        "domain jargon that sounds like common words when spoken: embedding, fine-tuning, chunking",
        "hyphenated terms: top-k, back-translation, few-shot"
    ]
}}

IMPORTANT: Include terms even if you are only 60% sure the candidate might say them.
It is better to over-include than miss a term.
Return ONLY valid JSON. No markdown, no explanation."""

    model = os.getenv("VOCAB_EXTRACTION_MODEL", "llama-3.3-70b-versatile")

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1200,
        )
        raw = (response.choices[0].message.content or "").strip()
        payload = _extract_json_payload(raw)
        normalized = _normalize_vocab_payload(payload)
        print(
            f"[vocab] domain={normalized['domain']} | "
            f"acronyms={len(normalized['acronyms'])} | "
            f"proper_nouns={len(normalized['proper_nouns'])} | "
            f"terms={len(normalized['terms'])}",
            flush=True,
        )
        print(f"[vocab] acronyms sample: {normalized['acronyms'][:10]}", flush=True)
        return normalized
    except Exception as e:
        print(f"[vocab] extraction failed: {e}", flush=True)
        return fallback


def generate_questions_with_vocab(resume_text: str, jd_text: str = "") -> tuple[list, dict]:
    """Generate interview questions and domain vocabulary in one call."""
    vocab = extract_vocab_from_resume(resume_text, jd_text=jd_text)
    questions = generate_questions(resume_text, jd_text=jd_text)
    return questions, vocab


def generate_questions_with_keywords(
    resume_text: str, jd_text: str = ""
) -> tuple[list, list, dict]:
    """
    Generate interview questions WITH per-question keywords for transcription.

    This is the key to accurate STT across ANY domain (management, AIML,
    healthcare, finance, etc.). Each question gets its own keyword list so
    Whisper only biases toward terms relevant to THAT specific answer.

    Returns:
        (questions, question_keywords, vocab)
        - questions: list of 5 question strings
        - question_keywords: list of 5 keyword lists (one per question)
        - vocab: full resume vocabulary dict
    """
    vocab = extract_vocab_from_resume(resume_text, jd_text=jd_text)
    questions, keywords = _generate_questions_and_keywords(resume_text, jd_text=jd_text)
    return questions, keywords, vocab


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
        print("[resume_parser] WARNING Very little text -- PDF may be image-based (scanned)", flush=True)
    return text


# ── Question generation ────────────────────────────────────────────────────

def generate_questions(resume_text: str, jd_text: str = "") -> list:
    resume_text = (resume_text or "").strip()
    jd_text     = (jd_text or "").strip()

    if not resume_text:
        print("[resume_parser] WARNING No resume text -- returning defaults", flush=True)
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


def _generate_questions_and_keywords(
    resume_text: str, jd_text: str = ""
) -> tuple[list, list]:
    """
    Generate questions AND per-question keywords in a single LLM call.
    Works for ANY domain: AIML, management, finance, healthcare, etc.

    Returns: (questions_list, keywords_list)
    """
    resume_text = (resume_text or "").strip()
    jd_text = (jd_text or "").strip()

    if not resume_text:
        qs = _default_questions()
        return qs, [[] for _ in qs]

    jd_block = ""
    jd_note = ""
    if jd_text:
        jd_block = f"\n=== JOB DESCRIPTION ===\n{jd_text[:2000]}\n"
        jd_note = " and job description"

    prompt = (
        "You are a senior interviewer preparing questions AND a speech-to-text keyword list.\n\n"
        "=== CANDIDATE RESUME ===\n"
        f"{resume_text[:3000]}\n"
        f"{jd_block}"
        f"Generate exactly 5 interview questions based on this resume{jd_note}.\n\n"
        "For EACH question, also provide 5-8 technical keywords/terms that the candidate\n"
        "would likely say when answering that specific question. These keywords help our\n"
        "speech-to-text system accurately transcribe domain-specific terms.\n\n"
        "Keyword guidelines:\n"
        "- Include acronyms the candidate might say (e.g. API, SQL, KPI, ROI, HIPAA)\n"
        "- Include tool/framework names (e.g. TensorFlow, Salesforce, SAP, Tableau)\n"
        "- Include domain jargon that could be misheard (e.g. modularity, stakeholder)\n"
        "- IMPORTANT: Include project names, product names, and company names from the resume\n"
        "  that the candidate would likely mention (e.g. PsySense, Agentic RAG, MyApp)\n"
        "- Only include terms RELEVANT to that specific question\n"
        "- For behavioral questions, include fewer or no keywords\n\n"
        'Return ONLY a JSON array of 5 objects. No markdown, no explanation:\n'
        '[\n'
        '  {"question": "Your interview question here?", "keywords": ["term1", "term2"]},\n'
        '  ...\n'
        ']'
    )

    print("[resume_parser] Generating questions + keywords...", flush=True)
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1200,
        )
        raw = response.choices[0].message.content.strip()
        print(f"[resume_parser] LLM replied ({len(raw)} chars): {raw[:150]!r}", flush=True)

        raw = re.sub(r"```json|```", "", raw).strip()

        # Parse the JSON array of objects
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            raw = match.group(0)

        data = json.loads(raw)

        if isinstance(data, list) and len(data) >= 5:
            questions = []
            keywords = []
            for item in data[:5]:
                if isinstance(item, dict):
                    questions.append(str(item.get("question", "")))
                    kw = item.get("keywords", [])
                    keywords.append([str(k) for k in kw] if isinstance(kw, list) else [])
                elif isinstance(item, str):
                    # Fallback: LLM returned plain strings
                    questions.append(item)
                    keywords.append([])

            if len(questions) >= 5:
                print(f"[resume_parser] OK {len(questions)} questions + keywords generated", flush=True)
                for i, (q, kw) in enumerate(zip(questions, keywords)):
                    print(f"  Q{i+1} keywords: {kw}", flush=True)
                return questions[:5], keywords[:5]

        print("[resume_parser] WARNING Could not parse Q+K format -- falling back", flush=True)
    except EnvironmentError:
        pass
    except Exception as e:
        print(f"[resume_parser] ERROR Q+K generation failed: {e}", flush=True)

    # Fallback: use regular question generation (no keywords)
    qs = generate_questions(resume_text, jd_text=jd_text)
    return qs, [[] for _ in qs]


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
            print(f"[resume_parser] OK {len(questions)} custom questions generated", flush=True)
            return [str(q) for q in questions[:5]]

        print(f"[resume_parser] WARNING Got {len(questions)} questions (need 5) -- using defaults", flush=True)
        return _default_questions()

    except EnvironmentError:
        return _default_questions()
    except json.JSONDecodeError as e:
        print(f"[resume_parser] ERROR JSON parse error: {e} | raw={raw!r}", flush=True)
        return _default_questions()
    except Exception as e:
        print(f"[resume_parser] ERROR LLM failed: {type(e).__name__}: {e}", flush=True)
        return _default_questions()


def _default_questions() -> list:
    print("[resume_parser] WARNING USING FALLBACK QUESTIONS", flush=True)
    return [
        "Walk me through a project you built end-to-end — what was your role and what did you deliver?",
        "Tell me about a time you had to learn a new technology quickly under pressure.",
        "Describe a situation where you disagreed with a technical decision made by your team.",
        "What's the most complex problem you've solved — how did you approach it?",
        "Why are you interested in this role, and what specifically makes you a strong fit?",
    ]