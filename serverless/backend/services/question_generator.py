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
    if not resume_text:
        questions = _default_questions()
        return questions, [[] for _ in questions], _default_vocab()

    api_key = _get_groq_api_key()
    if not api_key:
        questions = _default_questions()
        return questions, [[] for _ in questions], _default_vocab()

    payload = _call_groq(api_key, _build_prompt(resume_text, jd_text))
    questions, keywords = _parse_questions(payload)
    vocab = _compact_vocab(resume_text, jd_text, keywords)
    return questions, keywords, vocab


def _get_groq_api_key() -> str:
    env_key = os.environ.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY_2")
    if env_key:
        return env_key.strip()

    parameter_name = os.environ.get("GROQ_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return ""

    try:
        import boto3  # type: ignore
    except ImportError:
        return ""

    response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
    return str(response.get("Parameter", {}).get("Value", "")).strip()


def _build_prompt(resume_text: str, jd_text: str) -> str:
    jd_block = f"\n=== JOB DESCRIPTION ===\n{jd_text[:2000]}\n" if jd_text else ""
    return (
        "You are a senior interviewer preparing questions and speech-to-text keywords.\n\n"
        "=== CANDIDATE RESUME ===\n"
        f"{resume_text[:3000]}\n"
        f"{jd_block}"
        "Generate exactly 5 interview questions for this candidate"
        f"{' and role' if jd_text else ''}.\n"
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

    if len(questions) < 5:
        questions = _default_questions()
        keywords = [[] for _ in questions]

    return questions[:5], keywords[:5]


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
