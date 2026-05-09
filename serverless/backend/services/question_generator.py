"""Question generation wrapper for the serverless MVP."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any


def generate_questions_with_keywords(
    resume_text: str,
    jd_text: str = "",
    seed_context: str = "",
) -> tuple[list[str], list[list[str]], dict[str, Any]]:
    resume_text = (resume_text or "").strip()
    jd_text = (jd_text or "").strip()
    generation_seed = _generation_seed(resume_text, jd_text, seed_context)
    if not resume_text and not jd_text:
        questions = _default_questions()
        return questions, [[] for _ in questions], _default_vocab()

    fallback_questions, fallback_keywords = _contextual_fallback_questions(resume_text, jd_text, generation_seed)
    api_keys = _get_groq_api_keys()
    if not api_keys:
        return fallback_questions, fallback_keywords, _compact_vocab(resume_text, jd_text, fallback_keywords, generation_seed)

    for api_key in api_keys:
        try:
            payload = _call_groq(api_key, _build_prompt(resume_text, jd_text, generation_seed))
            questions, keywords = _parse_questions(payload)
            questions, keywords = _complete_questions(questions, keywords, fallback_questions, fallback_keywords)
            questions, keywords = _diversify_generic_questions(questions, keywords, fallback_questions, fallback_keywords)
            vocab = _compact_vocab(resume_text, jd_text, keywords, generation_seed)
            return questions, keywords, vocab
        except Exception:
            continue
    return fallback_questions, fallback_keywords, _compact_vocab(resume_text, jd_text, fallback_keywords, generation_seed)


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


def _build_prompt(resume_text: str, jd_text: str, generation_seed: str) -> str:
    jd_block = f"\n=== JOB DESCRIPTION ===\n{jd_text[:2000]}\n" if jd_text else ""
    focus_plan = _focus_plan(generation_seed)
    return (
        "You are a senior technical and behavioral interviewer preparing a personalized interview.\n\n"
        "=== CANDIDATE RESUME ===\n"
        f"{resume_text[:3000]}\n"
        f"{jd_block}"
        f"Interview variation seed: {generation_seed}. Use it only to vary the question angle; do not mention it.\n"
        f"This interview's focus plan: {focus_plan}.\n\n"
        "Generate exactly 5 distinct interview questions for this candidate"
        f"{' and role' if jd_text else ''}.\n"
        "Use concrete resume details, JD responsibilities, and likely gaps. Do not reuse generic repeated question sets.\n"
        "Avoid these exact or near-exact questions unless the wording is substantially more specific to the candidate:\n"
        "- Can you walk us through your experience with designing and developing machine learning models for classification, regression, and NLP tasks?\n"
        "- How do you approach building and maintaining data pipelines for model training and evaluation?\n"
        "- Can you describe your experience with deploying ML models as REST APIs using FastAPI or Flask?\n"
        "- How do you collaborate with product and engineering teams to integrate AI features into existing products?\n"
        "- Can you explain your approach to monitoring model performance and retraining as needed?\n\n"
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
        "temperature": float(os.environ.get("QUESTION_GENERATION_TEMPERATURE", "0.72")),
        "top_p": 0.9,
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


def _diversify_generic_questions(
    questions: list[str],
    keywords: list[list[str]],
    fallback_questions: list[str],
    fallback_keywords: list[list[str]],
) -> tuple[list[str], list[list[str]]]:
    if not questions or not fallback_questions:
        return questions, keywords
    diversified = list(questions)
    diversified_keywords = list(keywords)
    used = {_question_key(question) for question in diversified}
    for index, question in enumerate(list(diversified)):
        if not _is_generic_question(question):
            continue
        for fallback_index, fallback_question in enumerate(fallback_questions):
            fallback_key = _question_key(fallback_question)
            if fallback_key in used and fallback_key != _question_key(question):
                continue
            diversified[index] = fallback_question
            if index < len(diversified_keywords):
                diversified_keywords[index] = fallback_keywords[fallback_index] if fallback_index < len(fallback_keywords) else []
            used.add(fallback_key)
            break
    return diversified, diversified_keywords


def _is_generic_question(question: str) -> bool:
    normalized = question.lower()
    generic_markers = (
        "designing and developing machine learning models",
        "classification, regression, and nlp",
        "walk us through your experience",
        "describe your experience with",
        "building and maintaining data pipelines",
        "deploying ml models as rest apis",
        "using fastapi or flask",
        "collaborate with product and engineering teams",
        "monitoring model performance and retraining",
    )
    return any(marker in normalized for marker in generic_markers)


def _question_key(question: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()


def _compact_vocab(resume_text: str, jd_text: str, keywords: list[list[str]], generation_seed: str = "") -> dict[str, Any]:
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
        "questionGenerationSeed": generation_seed,
    }


def _contextual_fallback_questions(resume_text: str, jd_text: str, generation_seed: str = "") -> tuple[list[str], list[list[str]]]:
    resume_terms = _extract_terms(resume_text)
    jd_terms = _extract_terms(jd_text)
    combined_terms = _dedupe_terms(resume_terms + jd_terms)
    project_terms = _join_terms(resume_terms[:3], "a relevant project from your resume")
    role_terms = _join_terms(jd_terms[:3], "the core responsibilities in this role")
    technical_terms = _join_terms(combined_terms[:4], "the role's technical stack")
    delivery_terms = _join_terms(combined_terms[2:6] or combined_terms[:4], "the solution")

    variant = _seed_number(generation_seed)
    question_banks = [
        [
            f"Pick one resume project involving {project_terms}. What problem did it solve, what was your exact ownership, and how did you measure success?",
            f"Tell me about the most production-like work you did with {project_terms}. What broke, what did you change, and what was the result?",
            f"Choose a project from your resume that best matches this role. How did {project_terms} influence the design and delivery decisions?",
        ],
        [
            f"The JD emphasizes {role_terms}. Describe a past situation where you handled a similar responsibility, including one tradeoff you made.",
            f"Where is your strongest evidence for {role_terms}, and where would you need ramp-up time if hired for this role?",
            f"Imagine you joined this team next week and had to deliver work around {role_terms}. What would you reuse from your past experience?",
        ],
        [
            f"Design a reliable production workflow using {technical_terms}. How would you validate inputs, monitor failures, and decide when to rollback?",
            f"Suppose a feature using {technical_terms} suddenly starts giving poor results in production. How would you debug it end to end?",
            f"Walk through the architecture choices you would make for {technical_terms}, including data flow, API boundaries, and operational risks.",
        ],
        [
            "Tell me about a time you had to align product, engineering, or business stakeholders when the technical answer was not obvious.",
            "Describe a disagreement you had about scope, quality, timeline, or architecture. How did you move the team toward a decision?",
            "Give an example of when you had to explain a technical risk to a non-technical stakeholder and influence the next step.",
        ],
        [
            f"Give an example of a difficult bug, model issue, data issue, or production problem involving {delivery_terms}. How did you find the root cause and prevent it later?",
            f"Tell me about a time a solution involving {delivery_terms} did not work as expected. What signals told you it was failing?",
            f"What is one gap in your experience for this role, and how would you close it while delivering work involving {delivery_terms}?",
        ],
    ]
    questions = [bank[(variant + index) % len(bank)] for index, bank in enumerate(question_banks)]
    keyword_groups = [
        resume_terms[:8],
        jd_terms[:8],
        combined_terms[:8],
        ["stakeholders", "tradeoff", "communication", "ownership", "delivery"],
        combined_terms[:8] or ["debugging", "root cause", "monitoring", "prevention"],
    ]
    return questions, keyword_groups


def _generation_seed(resume_text: str, jd_text: str, seed_context: str = "") -> str:
    raw = f"{seed_context}|{time.time_ns()}|{resume_text[:500]}|{jd_text[:500]}"
    # A short stable-looking seed is enough to guide prompt diversity without exposing source text.
    import hashlib
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _seed_number(generation_seed: str) -> int:
    try:
        return int((generation_seed or "0")[:8], 16)
    except ValueError:
        return 0


def _focus_plan(generation_seed: str) -> str:
    plans = [
        "project evidence, production failure, stakeholder alignment, measurable impact, learning gap",
        "architecture tradeoffs, validation strategy, operational monitoring, ownership, role ramp-up",
        "delivery under constraints, data quality, API boundaries, collaboration conflict, prevention steps",
        "resume proof, JD gap, debugging depth, product integration, continuous improvement",
        "business outcome, technical depth, deployment risk, communication, post-release monitoring",
    ]
    return plans[_seed_number(generation_seed) % len(plans)]


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
