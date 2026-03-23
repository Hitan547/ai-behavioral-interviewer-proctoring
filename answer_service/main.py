"""
answer_service/main.py
----------------------
Answer Intelligence Service — Port 8000

Run with:
    uvicorn answer_service.main:app --port 8000 --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel

from answer_service.llm_engine import evaluate_answer
from answer_service.scoring import compute_cognitive_score

app = FastAPI(title="PsySense Answer Intelligence", version="2.0")


class AnswerRequest(BaseModel):
    question: str
    answer: str


@app.get("/")
def root():
    return {"message": "Answer Intelligence Service Running", "version": "2.0"}


@app.post("/evaluate_answer")
def evaluate(req: AnswerRequest):

    # Returns empty answer gracefully
    if not req.answer or not req.answer.strip():
        return {
            "dimension_scores": {
                "clarity": 0, "relevance": 0, "structure": 0,
                "depth": 0, "confidence": 0, "problem_solving": 0,
                "summary": "No answer provided.",
                "star_detected": False,
                "key_strength": "N/A",
                "key_improvement": "Provide a complete answer"
            },
            "cognitive_score": 0.0
        }

    scores = evaluate_answer(req.question, req.answer)

    # Pass question so scorer can weight dimensions correctly
    cognitive_score = compute_cognitive_score(scores, question=req.question)

    return {
        "dimension_scores": scores,
        "cognitive_score": cognitive_score
    }