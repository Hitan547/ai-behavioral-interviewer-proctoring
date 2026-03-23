"""
answer_service/scoring.py
-------------------------
Cognitive score computation with question-type aware weighting.

Why weighted instead of simple average:
- "Tell me about yourself" → problem_solving is barely applicable
- Behavioural questions → structure + depth matter most
- Technical questions   → problem_solving + depth matter most

Simple average punishes candidates unfairly when a dimension is
not relevant to the question type.
"""

from answer_service.prompt import classify_question

# ── Dimension weights per question type ───────────────────────────────────
# All sets of weights must sum to 1.0

_WEIGHTS = {
    "introduction": {
        "clarity":        0.25,
        "relevance":      0.25,
        "structure":      0.15,
        "depth":          0.15,
        "confidence":     0.15,
        "problem_solving": 0.05,   # barely applicable for intros
    },
    "behavioural": {
        "clarity":        0.15,
        "relevance":      0.20,
        "structure":      0.20,
        "depth":          0.20,
        "confidence":     0.10,
        "problem_solving": 0.15,
    },
    "technical": {
        "clarity":        0.20,
        "relevance":      0.15,
        "structure":      0.10,
        "depth":          0.20,
        "confidence":     0.10,
        "problem_solving": 0.25,
    },
    "general": {
        "clarity":        0.18,
        "relevance":      0.18,
        "structure":      0.18,
        "depth":          0.18,
        "confidence":     0.14,
        "problem_solving": 0.14,
    },
}


def compute_cognitive_score(scores: dict, question: str = "") -> float:
    """
    Compute weighted cognitive score (0–10) based on question type.

    Parameters
    ----------
    scores   : dict  — dimension scores from LLM
    question : str   — original interview question (used for type detection)

    Returns
    -------
    float  cognitive score 0–10, or 0.0 on error
    """
    try:
        q_type  = classify_question(question) if question else "general"
        weights = _WEIGHTS.get(q_type, _WEIGHTS["general"])

        weighted_sum = sum(
            scores[dim] * weight
            for dim, weight in weights.items()
            if dim in scores
        )

        return round(min(weighted_sum, 10.0), 2)

    except Exception:
        return 0.0