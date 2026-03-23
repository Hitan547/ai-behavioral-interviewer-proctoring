"""
insight_service/main.py
-----------------------
Recruiter Insight Engine — Port 8003

Run with:
    uvicorn insight_service.main:app --port 8003 --reload
"""

from fastapi import FastAPI
from insight_service.insight_engine import generate_insight

app = FastAPI(title="PsySense Insight Engine", version="2.0")


@app.get("/")
def home():
    return {"status": "Insight Service Running", "version": "2.0"}


@app.post("/generate_insight")
def insight(data: dict):
    avg_cognitive  = data.get("avg_cognitive",  5.0)
    avg_emotion    = data.get("avg_emotion",    5.0)
    avg_engagement = data.get("avg_engagement", 8.0)  # was being ignored before
    final_score    = data.get("final_score",    0.0)

    result = generate_insight(
        avg_cognitive  = avg_cognitive,
        avg_emotion    = avg_emotion,
        final_score    = final_score,
        avg_engagement = avg_engagement
    )

    return result