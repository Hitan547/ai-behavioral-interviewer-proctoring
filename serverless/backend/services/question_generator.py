"""Question generation wrapper for the serverless MVP."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


def generate_questions_with_keywords(resume_text: str, jd_text: str = "") -> tuple[list[str], list[list[str]], dict[str, Any]]:
    resume_text = (resume_text or "").strip()
    jd_text = (jd_text or "").strip()
    if not resume_text and not jd_text:
        questions = _default_questions()
        return questions, [[] for _ in questions], _default_vocab()

    fallback_questions, fallback_keywords = _contextual_fallback_questions(resume_text, jd_text)
    api_keys = _get_groq_api_keys()
    if not api_keys:
        return fallback_questions, fallback_keywords, _compact_vocab(resume_text, jd_text, fallback_keywords)

    for api_key in api_keys:
        try:
            payload = _call_groq(api_key, _build_prompt(resume_text, jd_text))
            questions, keywords = _parse_questions(payload)
            questions, keywords = _complete_questions(questions, keywords, fallback_questions, fallback_keywords)
            questions, keywords = _diversify_generic_opening(questions, keywords, fallback_questions, fallback_keywords)
            vocab = _compact_vocab(resume_text, jd_text, keywords)
            return questions, keywords, vocab
        except Exception:
            continue
    return fallback_questions, fallback_keywords, _compact_vocab(resume_text, jd_text, fallback_keywords)


def _get_groq_api_keys() -> list[str]:
    keys: list[str] = []
    for env_name in ("GROQ_API_KEY", "GROQ_API_KEY_2"):
        env_key = os.environ.get(env_name, "").strip()
        if env_key and env_key not in keys:
            keys.append(env_key)

    parameter_name = os.environ.get("GROQ_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return keys

    try:
        import boto3  # type: ignore
    except ImportError:
        return keys

    response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
    ssm_key = str(response.get("Parameter", {}).get("Value", "")).strip()
    if ssm_key and ssm_key not in keys:
        keys.append(ssm_key)
    return keys


def _build_prompt(resume_text: str, jd_text: str) -> str:
    jd_block = f"\n=== JOB DESCRIPTION ===\n{jd_text[:2000]}\n" if jd_text else ""
    return (
        "You are a senior technical and behavioral interviewer preparing a personalized interview.\n\n"
        "=== CANDIDATE RESUME ===\n"
        f"{resume_text[:3000]}\n"
        f"{jd_block}"
        "Generate exactly 5 distinct interview questions for this candidate"
        f"{' and role' if jd_text else ''}.\n"
        "Use concrete resume details, JD responsibilities, and likely gaps. Avoid generic repeated openings like "
        "\"walk us through your experience with designing and developing machine learning models\".\n"
        "Question mix:\n"
        "1. One concrete project or achievement from the resume that maps to the JD.\n"
        "2. One JD-critical skill or responsibility, including how they handled it in practice.\n"
        "3. One technical depth question about implementation, deployment, data, reliability, or tradeoffs.\n"
        "4. One collaboration/ownership behavioral question tied to the role.\n"
        "5. One gap, learning, debugging, or production-readiness question.\n"
        "For each question, provide 5-8 relevant keywords the candidate may say.\n\n"
        "Return only this JSON object with no markdown:\n"
        '{"questions":[{"question":"Question?","keywords":["term"]}]}'
    )


def _call_groq(api_key: str, prompt: str) -> str:
    body = json.dumps({
        "model": os.environ.get("QUESTION_GENERATION_MODEL", "llama-3.1-8b-instant"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1200,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TalentryxAIServerless/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Question generation provider request failed.") from exc
    return str(data["choices"][0]["message"]["content"])


def _parse_questions(raw: str) -> tuple[list[str], list[list[str]]]:
    cleaned = re.sub(r"```json|```", "", raw or "").strip()
    parsed: Any
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not match:
            parsed = {}
        else:
            parsed = json.loads(match.group(0))

    entries = parsed.get("questions") if isinstance(parsed, dict) else parsed
    questions: list[str] = []
    keywords: list[list[str]] = []

    if isinstance(entries, list):
        for entry in entries[:5]:
            if isinstance(entry, dict):
                question = str(entry.get("question", "")).strip()
                raw_keywords = entry.get("keywords", [])
                entry_keywords = [str(term).strip() for term in raw_keywords if str(term).strip()] if isinstance(raw_keywords, list) else []
            else:
                question = str(entry).strip()
                entry_keywords = []
            if question:
                questions.append(question)
                keywords.append(entry_keywords[:8])

    return questions[:5], keywords[:5]


def _complete_questions(
    questions: list[str],
    keywords: list[list[str]],
    fallback_questions: list[str],
    fallback_keywords: list[list[str]],
) -> tuple[list[str], list[list[str]]]:
    completed_questions = list(questions[:5])
    completed_keywords = list(keywords[:5])
    seen = {_question_key(question) for question in completed_questions}
    for index, question in enumerate(fallback_questions):
        if len(completed_questions) >= 5:
            break
        key = _question_key(question)
        if key in seen:
            continue
        completed_questions.append(question)
        completed_keywords.append(fallback_keywords[index] if index < len(fallback_keywords) else [])
        seen.add(key)
    if len(completed_questions) < 5:
        defaults = _default_questions()
        for question in defaults:
            if len(completed_questions) >= 5:
                break
            completed_questions.append(question)
            completed_keywords.append([])
    return completed_questions[:5], completed_keywords[:5]


def _diversify_generic_opening(
    questions: list[str],
    keywords: list[list[str]],
    fallback_questions: list[str],
    fallback_keywords: list[list[str]],
) -> tuple[list[str], list[list[str]]]:
    if not questions:
        return questions, keywords
    opening = questions[0].lower()
    generic_markers = (
        "designing and developing machine learning models",
        "classification, regression, and nlp",
        "walk us through your experience with",
        "describe your experience with",
    )
    if any(marker in opening for marker in generic_markers) and fallback_questions:
        diversified = list(questions)
        diversified_keywords = list(keywords)
        diversified[0] = fallback_questions[0]
        diversified_keywords[0] = fallback_keywords[0] if fallback_keywords else []
        return diversified, diversified_keywords
    return questions, keywords


def _question_key(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


def _compact_vocab(resume_text: str, jd_text: str, keywords: list[list[str]]) -> dict[str, Any]:
    seen = set()
    terms = []
    for keyword_list in keywords:
        for term in keyword_list:
            key = term.casefold()
            if key not in seen:
                seen.add(key)
                terms.append(term)
    return {
        "domain": "general",
        "subDomain": "",
        "terms": terms[:50],
        "sourceLengths": {
            "resume": len(resume_text or ""),
            "jd": len(jd_text or ""),
        },
    }


def _contextual_fallback_questions(resume_text: str, jd_text: str) -> tuple[list[str], list[list[str]]]:
    resume_terms = _extract_terms(resume_text)
    jd_terms = _extract_terms(jd_text)
    combined_terms = _dedupe_terms(resume_terms + jd_terms)
    project_terms = _join_terms(resume_terms[:3], "a relevant project from your resume")
    role_terms = _join_terms(jd_terms[:3], "the core responsibilities in this role")
    technical_terms = _join_terms(combined_terms[:4], "the role's technical stack")
    delivery_terms = _join_terms(combined_terms[2:6] or combined_terms[:4], "the solution")

    questions = [
        f"Your resume mentions {project_terms}. Walk me through one specific project where you used this and what measurable result you delivered.",
        f"This role needs {role_terms}. Which part of your past work is closest to that requirement, and what would you need to ramp up on?",
        f"Describe how you would design, validate, and deploy a production solution using {technical_terms}. What tradeoffs would you watch?",
        "Tell me about a time you worked with product, engineering, or business stakeholders to turn a technical idea into a usable feature.",
        f"Give an example of a difficult bug, model issue, data issue, or production problem involving {delivery_terms}. How did you find the root cause and prevent it later?",
    ]
    keyword_groups = [
        resume_terms[:8],
        jd_terms[:8],
        combined_terms[:8],
        ["stakeholders", "tradeoff", "communication", "ownership", "delivery"],
        combined_terms[:8] or ["debugging", "root cause", "monitoring", "prevention"],
    ]
    return questions, keyword_groups


def _extract_terms(text: str) -> list[str]:
    text = text or ""
    patterns = [
        "FastAPI", "Flask", "Django", "React", "Node.js", "TypeScript", "JavaScript",
        "Python", "Java", "SQL", "PostgreSQL", "MongoDB", "DynamoDB", "AWS", "Lambda",
        "S3", "API Gateway", "Docker", "Kubernetes", "CI/CD", "GitHub Actions",
        "machine learning", "ML", "AI", "LLM", "NLP", "classification", "regression",
        "computer vision", "data pipelines", "MLOps", "model deployment", "monitoring",
        "data drift", "retraining", "REST API", "microservices", "SaaS",
    ]
    terms: list[str] = []
    for pattern in patterns:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(pattern)}(?![A-Za-z0-9])", text, re.IGNORECASE):
            terms.append(pattern)
    for phrase in re.findall(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2}\b", text):
        clean = phrase.strip()
        if 2 < len(clean) <= 40 and clean.lower() not in {"candidate resume", "job description"}:
            terms.append(clean)
    return _dedupe_terms(terms)[:16]


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen = set()
    output: list[str] = []
    for term in terms:
        clean = re.sub(r"\s+", " ", str(term)).strip()
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(clean)
    return output


def _join_terms(terms: list[str], fallback: str) -> str:
    clean_terms = _dedupe_terms(terms)
    if not clean_terms:
        return fallback
    if len(clean_terms) == 1:
        return clean_terms[0]
    return ", ".join(clean_terms[:-1]) + f", and {clean_terms[-1]}"


def _default_vocab() -> dict[str, Any]:
    return {
        "domain": "general",
        "subDomain": "",
        "terms": [],
        "sourceLengths": {"resume": 0, "jd": 0},
    }


def _default_questions() -> list[str]:
    return [
        "Walk me through a project you built end-to-end. What was your role and what did you deliver?",
        "Tell me about a time you had to learn a new technology quickly under pressure.",
        "Describe a situation where you disagreed with a technical decision made by your team.",
        "What is the most complex problem you have solved, and how did you approach it?",
        "Why are you interested in this role, and what specifically makes you a strong fit?",
    ]
