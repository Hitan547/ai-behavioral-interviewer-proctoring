import os
import sys
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from services.question_generator import generate_questions_with_keywords


def test_question_generator_includes_workplace_behavior_questions(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY_2", raising=False)
    monkeypatch.delenv("GROQ_API_KEY_PARAMETER_NAME", raising=False)

    questions, keywords, vocab = generate_questions_with_keywords(
        "Asha built ML models, FastAPI services, data pipelines, AWS Lambda workflows, and monitoring automation.",
        "Hire an AIML engineer who can deploy models, collaborate with product teams, debug production issues, and improve model reliability.",
        seed_context="unit-test",
    )

    behavioral_markers = (
        "tell me about a time",
        "describe a situation",
        "give an example",
        "stakeholder",
        "feedback",
    )
    repeated_generic = "designing and developing machine learning models for classification, regression, and nlp"

    assert len(questions) == 5
    assert len(keywords) == 5
    assert vocab["questionGenerationSeed"]
    assert sum(
        1
        for question in questions
        if any(marker in question.lower() for marker in behavioral_markers)
    ) >= 2
    assert all(repeated_generic not in question.lower() for question in questions)
