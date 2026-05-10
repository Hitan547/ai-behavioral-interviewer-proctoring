"""
engagement_service/main.py
--------------------------
FastAPI microservice for standalone engagement detection.
Runs on port 8004.

Endpoints
---------
GET  /          → health check
GET  /detect    → opens webcam for 10 s, returns engagement score
POST /detect    → same, but accepts { "duration": N } to customise window

Run with:
    uvicorn engagement_service.main:app --port 8004 --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel
import sys
import os

# Allow running from project root: python -m uvicorn engagement_service.main:app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def compute_engagement_score(duration: int = 10):
    from engagement_realtime import compute_engagement_score as _fn
    return _fn(duration)

app = FastAPI(title="PsySense Engagement Service", version="1.0")


class DetectRequest(BaseModel):
    duration: int = 10   # seconds to sample webcam


@app.get("/")
def home():
    return {"status": "Engagement Service Running", "port": 8004}


@app.get("/health")
def health():
    return {"status": "ok", "service": "engagement_service", "version": "1.0"}


@app.get("/detect")
def detect_get():
    if os.getenv("ENVIRONMENT") == "production":
        return {"error": "Not available in production. Interview uses WebRTC."}
    score = compute_engagement_score(duration=10)
    return {"engagement_score": score}


@app.post("/detect")
def detect_post(req: DetectRequest):
    """Custom-duration webcam sample."""
    if os.getenv("ENVIRONMENT") == "production":
        return {"error": "Not available in production. Interview uses WebRTC."}
    score = compute_engagement_score(duration=req.duration)
    return {"engagement_score": score}
