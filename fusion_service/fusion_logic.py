def compute_final_score(cognitive_score, emotion_score):
    """
    Mini Fusion:
    70% Cognitive
    30% Emotion
    """

    final_score_10 = (0.7 * cognitive_score) + (0.3 * emotion_score)

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