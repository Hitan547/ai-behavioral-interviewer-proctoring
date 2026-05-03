"""
insight_service/insight_engine.py
----------------------------------
Generates recruiter insights from behavioral scores.

Fixes vs original:
- Always returns at least one weakness — even strong candidates have areas to grow
- Uses engagement score (was being ignored)
- More nuanced thresholds
- Better recommendation labels
"""


def generate_insight(avg_cognitive: float, avg_emotion: float,
                     final_score: float, avg_engagement: float = 8.0) -> dict:

    strengths  = []
    weaknesses = []

    # ── Cognitive analysis ────────────────────────────────────────────────
    if avg_cognitive >= 8:
        strengths.append("excellent answer structure with clear reasoning and examples")
    elif avg_cognitive >= 6.5:
        strengths.append("strong structured thinking and clear communication")
    elif avg_cognitive >= 5:
        strengths.append("moderate clarity and logical explanation ability")
        weaknesses.append("needs deeper reasoning and better structured storytelling")
    else:
        weaknesses.append("answers lack structure, depth and clear reasoning")

    # ── Delivery / communication analysis ─────────────────────────────────
    if avg_emotion >= 7.5:
        strengths.append("clear delivery and steady communication")
    elif avg_emotion >= 6:
        strengths.append("generally steady communication delivery")
        weaknesses.append("could improve vocal energy and delivery clarity")
    elif avg_emotion >= 4:
        weaknesses.append("delivery showed hesitation and should be reviewed")
    else:
        weaknesses.append("delivery signal needs review for clarity and steadiness")

    # ── Engagement analysis ───────────────────────────────────────────────
    if avg_engagement >= 8:
        strengths.append("excellent eye contact and attentiveness throughout")
    elif avg_engagement >= 6:
        strengths.append("good visual engagement during the interview")
        weaknesses.append("maintain more consistent eye contact with the camera")
    else:
        weaknesses.append("low visual engagement — ensure camera is visible and maintain eye contact")

    # ── Always add at least one improvement area ──────────────────────────
    # Even strong candidates should have something to work on
    if not weaknesses:
        if avg_cognitive < 9:
            weaknesses.append("consider adding more specific measurable outcomes to answers (e.g. improved X by Y%)")
        else:
            weaknesses.append("continue developing leadership and strategic thinking for senior roles")

    # ── Recommendation ────────────────────────────────────────────────────
    if final_score >= 80:
        recommendation = "Strong Hire — Recommend Fast Track"
    elif final_score >= 70:
        recommendation = "Strong Hire"
    elif final_score >= 55:
        recommendation = "Potential Hire with Training"
    elif final_score >= 35:
        recommendation = "Needs Improvement — Consider Second Round"
    else:
        recommendation = "Needs Significant Improvement"

    # ── Summary ───────────────────────────────────────────────────────────
    summary = (
        f"The candidate demonstrates {', '.join(strengths) if strengths else 'developing skills'} "
        f"with areas to improve in {', '.join(weaknesses)}. "
        f"Overall evaluation: {recommendation}."
    )

    return {
        "strengths":       strengths,
        "weaknesses":      weaknesses,
        "recommendation":  recommendation,
        "final_summary":   summary
    }
