def compute_final_score(cognitive_score, emotion_score, engagement_score=5.0):
    """
    Mini Fusion:
    70% Answer Quality
    15% Delivery Signal (emotion_score wire field kept for compatibility)
    15% Attentiveness
    """

    final_score_10 = (
        (0.70 * cognitive_score)
        + (0.15 * emotion_score)
        + (0.15 * engagement_score)
    )

    final_score_100 = round(final_score_10 * 10, 2)

    return final_score_100


def readiness_level(score):
    if score >= 80:
        return "Excellent"
    elif score >= 65:
        return "Good"
    elif score >= 50:
        return "Moderate"
    else:
        return "Needs Improvement"
