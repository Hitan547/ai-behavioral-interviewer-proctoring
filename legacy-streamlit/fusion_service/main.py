"""
fusion_service/main.py
----------------------
Behavioral Fusion Engine — Port 8001

Formula:
    raw  = 0.70 × cognitive  +  0.15 × delivery  +  0.15 × engagement
    final_behavioral_score (0–100) = round(raw × 10, 1)

Readiness levels:
    ≥ 75  → Strong Candidate
    ≥ 55  → Moderate Candidate
    ≥ 35  → Needs Improvement
    <  35 → Significant Development Needed

Run with:
    uvicorn fusion_service.main:app --port 8001 --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="PsySense Fusion Engine", version="2.0")


class FusionRequest(BaseModel):
    cognitive_score:  float   # 0–10
    emotion_score:    float   # 0-10, kept for compatibility; treated as delivery signal
    engagement_score: float = 5.0   # 0-10, defaults to neutral if not provided


class FusionResponse(BaseModel):
    cognitive_score:         float
    emotion_score:           float
    delivery_score:          float
    engagement_score:        float
    raw_score:               float   # 0–10 before scaling
    final_behavioral_score:  float   # 0–100
    readiness_level:         str
    score_breakdown:         dict


def _readiness(score: float) -> str:
    if score >= 75:
        return "Strong Candidate"
    elif score >= 55:
        return "Moderate Candidate"
    elif score >= 35:
        return "Needs Improvement"
    else:
        return "Significant Development Needed"


@app.get("/")
def home():
    return {"status": "Fusion Engine Running", "port": 8001, "version": "2.0"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "fusion_service", "version": "2.0"}


@app.post("/fuse", response_model=FusionResponse)
def fuse(req: FusionRequest):
    # Clamp all inputs to 0–10
    cog = max(0.0, min(10.0, req.cognitive_score))
    emo = max(0.0, min(10.0, req.emotion_score))
    eng = max(0.0, min(10.0, req.engagement_score))

    # Weighted fusion. emotion_score is retained as the wire name, but it now
    # represents delivery/communication rather than emotional state.
    raw = (
        0.70 * cog
        + 0.15 * emo
        + 0.15 * eng
    )

    final = round(raw * 10, 1)   # scale 0–10 → 0–100

    return FusionResponse(
        cognitive_score        = round(cog, 2),
        emotion_score          = round(emo, 2),
        delivery_score         = round(emo, 2),
        engagement_score       = round(eng, 2),
        raw_score              = round(raw, 3),
        final_behavioral_score = final,
        readiness_level        = _readiness(final),
        score_breakdown        = {
            "cognitive_contribution":   round(0.70 * cog * 10, 1),
            "emotion_contribution":     round(0.15 * emo * 10, 1),
            "delivery_contribution":    round(0.15 * emo * 10, 1),
            "engagement_contribution":  round(0.15 * eng * 10, 1),
        }
    )
