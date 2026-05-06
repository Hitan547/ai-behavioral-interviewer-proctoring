"""Serverless scoring logic for interview submissions."""

from __future__ import annotations

from typing import Any


def score_interview(
    *,
    job: dict[str, Any],
    candidate: dict[str, Any],
    submission: dict[str, Any],
) -> dict[str, Any]:
    questions = candidate.get("questions") or []
    answers = submission.get("answers") or []
    answers_by_index = {
        int(answer.get("questionIndex", -1)): str(answer.get("answerText", "")).strip()
        for answer in answers
        if isinstance(answer, dict)
    }

    per_question = []
    for index, question in enumerate(questions):
        answer_text = answers_by_index.get(index, "")
        per_question.append(_score_answer(index, str(question), answer_text, str(job.get("jdText", ""))))

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


def summarize_integrity_risk(signals: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(signals, dict):
        signals = {}
    tab_switches = _non_negative_int(signals.get("tabSwitches", 0))
    fullscreen_exits = _non_negative_int(signals.get("fullscreenExits", 0))
    copy_paste_attempts = _non_negative_int(signals.get("copyPasteAttempts", 0))
    devtools_attempts = _non_negative_int(signals.get("devtoolsAttempts", 0))

    raw_risk = (
        tab_switches * 2
        + fullscreen_exits * 3
        + copy_paste_attempts * 4
        + devtools_attempts * 5
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
        "eventCount": len(signals.get("events", [])) if isinstance(signals.get("events"), list) else 0,
    }


def _score_answer(index: int, question: str, answer: str, jd_text: str) -> dict[str, Any]:
    if not answer:
        return {
            "questionIndex": index,
            "question": question,
            "answered": False,
            "score": 0,
            "verdict": "Missing",
            "summary": "No answer submitted.",
        }

    word_count = len(answer.split())
    question_terms = _terms(question)
    jd_terms = _terms(jd_text)
    answer_terms = _terms(answer)
    relevance_hits = len((question_terms | jd_terms) & answer_terms)

    length_score = min(35, word_count * 2)
    relevance_score = min(35, relevance_hits * 7)
    structure_score = _structure_score(answer)
    score = max(25, min(100, length_score + relevance_score + structure_score))

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
        "summary": f"Answer length {word_count} words with {relevance_hits} role/question term matches.",
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
