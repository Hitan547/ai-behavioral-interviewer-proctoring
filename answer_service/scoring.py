"""
answer_service/scoring.py
-------------------------
Recruiter-calibrated cognitive score computation.

Dimensions (updated to match new rubric):
  clarity, relevance, star_quality, specificity, communication, job_fit

Why question-type weights matter:
- "Why this role?" → job_fit and relevance dominate
- Behavioural      → star_quality and specificity dominate
- Technical        → specificity and clarity dominate
- Introduction     → clarity and communication dominate

All weight sets must sum to 1.0.
"""

from answer_service.prompt import classify_question

# ── Dimension weights per question type ───────────────────────────────────

_WEIGHTS = {
    "introduction": {
        "clarity":       0.25,   # Can I follow this person's story?
        "relevance":     0.20,   # Does it address the question?
        "star_quality":  0.10,   # Light — narrative structure is fine here
        "specificity":   0.15,   # Real background details matter
        "communication": 0.20,   # First impression — confidence counts
        "job_fit":       0.10,   # Does their background fit the role?
    },

    "behavioural": {
        "clarity":       0.15,
        "relevance":     0.15,
        "star_quality":  0.25,   # STAR is the core ask here
        "specificity":   0.25,   # Real examples are non-negotiable
        "communication": 0.10,
        "job_fit":       0.10,
    },

    "technical": {
        "clarity":       0.20,   # Can a recruiter follow this to present it?
        "relevance":     0.15,
        "star_quality":  0.05,   # Minimal — structure matters less
        "specificity":   0.30,   # Core signal: do they actually know this?
        "communication": 0.10,
        "job_fit":       0.20,   # Does the answer show readiness for THIS role?
    },

    "fit": {
        "clarity":       0.10,
        "relevance":     0.20,   # Did they answer the actual question?
        "star_quality":  0.05,   # Not really applicable
        "specificity":   0.15,   # Did they reference real research/experience?
        "communication": 0.15,
        "job_fit":       0.35,   # This IS the question — fit is everything
    },

    "general": {
        "clarity":       0.18,
        "relevance":     0.18,
        "star_quality":  0.16,
        "specificity":   0.18,
        "communication": 0.15,
        "job_fit":       0.15,
    },
}

# Map old dimension names → new names for backward compat with any callers
# that still pass the old keys (structure, depth, confidence, problem_solving)
_LEGACY_MAP = {
    "structure":       "star_quality",
    "depth":           "specificity",
    "confidence":      "communication",
    "problem_solving": "job_fit",
}


def compute_cognitive_score(scores: dict, question: str = "") -> float:
    """
    Compute weighted cognitive score (0–10) based on question type.

    Parameters
    ----------
    scores   : dict  — dimension scores from LLM (new or legacy keys both work)
    question : str   — original interview question (used for type detection)

    Returns
    -------
    float  — cognitive score 0–10, or 0.0 on error
    """
    try:
        # Normalise: remap legacy keys if LLM still uses old names
        normalised = {}
        for k, v in scores.items():
            key = _LEGACY_MAP.get(k, k)
            normalised[key] = v

        q_type  = classify_question(question) if question else "general"
        weights = _WEIGHTS.get(q_type, _WEIGHTS["general"])

        weighted_sum = sum(
            normalised[dim] * weight
            for dim, weight in weights.items()
            if dim in normalised
        )

        return round(min(weighted_sum, 10.0), 2)

    except Exception:
        return 0.0


def get_recruiter_verdict(scores: dict) -> str:
    """
    Return a human-readable recruiter verdict from the raw scores.
    Falls back gracefully if 'recruiter_verdict' key is missing.
    """
    # Prefer LLM-generated verdict if present
    if "recruiter_verdict" in scores:
        return scores["recruiter_verdict"]

    # Compute from score average as fallback
    dims = ["clarity", "relevance", "star_quality", "specificity", "communication", "job_fit"]
    valid = [scores[d] for d in dims if d in scores]
    if not valid:
        return "Borderline"

    avg = sum(valid) / len(valid)
    if avg >= 8:
        return "Strong Advance"
    if avg >= 6.5:
        return "Advance"
    if avg >= 4.5:
        return "Borderline"
    return "Do Not Advance"