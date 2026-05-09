"""
tests/test_api_endpoints.py
---------------------------
Integration tests for FastAPI microservice endpoints using TestClient.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ── Answer Service ───────────────────────────────────────────────────────


class TestAnswerService:
    @pytest.fixture
    def client(self):
        # Must mock Groq client before importing the module
        with patch("answer_service.llm_engine.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_groq_cls.return_value = mock_client

            # Mock the completions response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '''{
                "clarity": 7,
                "relevance": 8,
                "star_quality": 6,
                "specificity": 7,
                "communication": 7,
                "job_fit": 6,
                "summary": "Good answer with clear examples.",
                "star_detected": true,
                "key_strength": "Clear structure",
                "key_improvement": "More metrics needed",
                "recruiter_verdict": "Advance",
                "star_components": {
                    "situation": true, "task": true,
                    "action": true, "result": false
                }
            }'''
            mock_client.chat.completions.create.return_value = mock_response

            # Need to reload the module to pick up the mock
            import importlib
            import answer_service.llm_engine
            importlib.reload(answer_service.llm_engine)

            from answer_service.main import app
            yield TestClient(app)

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "answer_service"

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Running" in response.json()["message"]

    def test_evaluate_empty_answer(self, client):
        response = client.post("/evaluate_answer", json={
            "question": "Tell me about yourself",
            "answer": "",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["cognitive_score"] == 0.0
        assert data["recruiter_verdict"] == "Do Not Advance"

    def test_evaluate_with_answer(self, client):
        response = client.post("/evaluate_answer", json={
            "question": "Tell me about a time you led a project",
            "answer": "In my previous role at TechCorp, I led a team of 5 engineers...",
            "jd_text": "Senior software engineer role requiring leadership experience",
        })
        assert response.status_code == 200
        data = response.json()
        assert "dimension_scores" in data
        assert "cognitive_score" in data
        assert "recruiter_verdict" in data
        assert data["cognitive_score"] > 0


# ── Test other service health endpoints ──────────────────────────────────

class TestFusionServiceHealth:
    def test_health(self):
        try:
            from fusion_service.main import app
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
        except ImportError:
            pytest.skip("fusion_service not importable")


class TestInsightServiceHealth:
    def test_health(self):
        try:
            from insight_service.main import app
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200
        except ImportError:
            pytest.skip("insight_service not importable")
