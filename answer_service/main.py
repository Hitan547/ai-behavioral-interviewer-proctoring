"""
answer_service/main.py
----------------------
Answer Intelligence Service — Port 8000

Run with:
    uvicorn answer_service.main:app --port 8000 --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from answer_service.llm_engine import evaluate_answer
from answer_service.scoring import compute_cognitive_score

app = FastAPI(title="PsySense Answer Intelligence", version="3.0")


class AnswerRequest(BaseModel):
    question: str
    answer:   str
    jd_text:  Optional[str] = ""


@app.get("/")
def root():
    return {"message": "Answer Intelligence Service Running", "version": "3.0"}


@app.post("/evaluate_answer")
def evaluate(req: AnswerRequest):
    if not req.answer or not req.answer.strip():
        empty = {
            "clarity": 0, "relevance": 0, "star_quality": 0,
            "specificity": 0, "communication": 0, "job_fit": 0,
            "summary": "No answer provided.",
            "star_detected": False,
            "key_strength": "N/A",
            "key_improvement": "Provide a complete answer",
            "recruiter_verdict": "Do Not Advance",
            "star_components": {
                "situation": False, "task": False, "action": False, "result": False
            },
        }
        return {
            "dimension_scores":  empty,
            "cognitive_score":   0.0,
            "recruiter_verdict": "Do Not Advance",
        }

    scores = evaluate_answer(req.question, req.answer, jd_text=req.jd_text or "")
    cognitive_score = compute_cognitive_score(scores, question=req.question)

    # Use the verdict the LLM already produced — avoids double-computation
    verdict = scores.get("recruiter_verdict", "Borderline")

    return {
        "dimension_scores":  scores,
        "cognitive_score":   cognitive_score,
        "recruiter_verdict": verdict,
    }