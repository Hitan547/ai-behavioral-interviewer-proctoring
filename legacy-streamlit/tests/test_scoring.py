"""
tests/test_scoring.py
---------------------
Tests for the answer scoring engine: dimension weights, question classification,
cognitive score computation, and recruiter verdict logic.
"""

import pytest
from answer_service.scoring import compute_cognitive_score, get_recruiter_verdict
from answer_service.prompt import classify_question


# ── Question Classification ──────────────────────────────────────────────


class TestClassifyQuestion:
    def test_introduction(self):
        assert classify_question("Tell me about yourself") == "introduction"
        assert classify_question("Walk me through your background") == "introduction"

    def test_behavioural(self):
        assert classify_question("Tell me about a time you faced a challenge") == "behavioural"
        assert classify_question("Describe a situation where you worked under pressure") == "behavioural"
        assert classify_question("Give me an example of teamwork") == "behavioural"

    def test_technical(self):
        assert classify_question("How would you design a caching system?") == "technical"
        assert classify_question("Explain the difference between SQL and NoSQL") == "technical"

    def test_fit(self):
        assert classify_question("Why do you want this role?") == "fit"
        assert classify_question("What motivates you about this company?") == "fit"
        assert classify_question("Why should we hire you?") == "fit"

    def test_general_fallback(self):
        assert classify_question("What are your hobbies?") == "general"
        assert classify_question("") == "general"


# ── Cognitive Score Computation ──────────────────────────────────────────


class TestComputeCognitiveScore:
    def test_with_valid_scores(self, sample_scores):
        score = compute_cognitive_score(sample_scores, "Tell me about a time you led a team")
        assert 0 <= score <= 10
        assert isinstance(score, float)

    def test_with_zero_scores(self, empty_scores):
        score = compute_cognitive_score(empty_scores, "Tell me about yourself")
        assert score == 0.0

    def test_with_perfect_scores(self):
        perfect = {
            "clarity": 10, "relevance": 10, "star_quality": 10,
            "specificity": 10, "communication": 10, "job_fit": 10,
        }
        score = compute_cognitive_score(perfect, "general question")
        assert score == 10.0

    def test_different_question_types_produce_different_weights(self, sample_scores):
        score_intro = compute_cognitive_score(sample_scores, "Tell me about yourself")
        score_behav = compute_cognitive_score(sample_scores, "Tell me about a time you failed")
        score_tech = compute_cognitive_score(sample_scores, "How would you design a REST API?")
        # Scores should differ because different weights are applied
        scores = {score_intro, score_behav, score_tech}
        assert len(scores) >= 2, "Different question types should produce different scores"

    def test_legacy_key_remapping(self):
        """Old dimension names (structure, depth, etc.) should map to new names."""
        legacy_scores = {
            "clarity": 7, "relevance": 7,
            "structure": 8,       # should map to star_quality
            "depth": 9,           # should map to specificity
            "confidence": 7,      # should map to communication
            "problem_solving": 6, # should map to job_fit
        }
        score = compute_cognitive_score(legacy_scores, "general question")
        assert score > 0, "Legacy keys should be handled gracefully"

    def test_empty_question(self, sample_scores):
        """No question text should default to 'general' weights."""
        score = compute_cognitive_score(sample_scores, "")
        assert 0 <= score <= 10

    def test_handles_exception_gracefully(self):
        """Bad input should return 0.0, not raise."""
        assert compute_cognitive_score(None, "q") == 0.0
        assert compute_cognitive_score("not a dict", "q") == 0.0


# ── Recruiter Verdict ────────────────────────────────────────────────────


class TestRecruiterVerdict:
    def test_strong_advance(self):
        scores = {
            "clarity": 9, "relevance": 9, "star_quality": 8,
            "specificity": 9, "communication": 9, "job_fit": 8,
        }
        assert get_recruiter_verdict(scores) == "Strong Advance"

    def test_advance(self):
        scores = {
            "clarity": 7, "relevance": 7, "star_quality": 7,
            "specificity": 7, "communication": 6, "job_fit": 7,
        }
        assert get_recruiter_verdict(scores) == "Advance"

    def test_borderline(self):
        scores = {
            "clarity": 5, "relevance": 5, "star_quality": 5,
            "specificity": 4, "communication": 5, "job_fit": 5,
        }
        assert get_recruiter_verdict(scores) == "Borderline"

    def test_do_not_advance(self):
        scores = {
            "clarity": 2, "relevance": 3, "star_quality": 1,
            "specificity": 2, "communication": 3, "job_fit": 2,
        }
        assert get_recruiter_verdict(scores) == "Do Not Advance"

    def test_prefers_llm_verdict_when_present(self, sample_scores):
        """If LLM returned a verdict, use it instead of computing."""
        sample_scores["recruiter_verdict"] = "Strong Advance"
        assert get_recruiter_verdict(sample_scores) == "Strong Advance"

    def test_empty_scores_returns_borderline(self):
        assert get_recruiter_verdict({}) == "Borderline"
