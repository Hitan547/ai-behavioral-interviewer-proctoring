"""
tests/conftest.py
-----------------
Shared pytest fixtures for PsySense test suite.
"""

import os
import sys
import pytest

# Ensure the project root is importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force SQLite in-memory for all tests — never touch the real database.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GROQ_API_KEY"] = "gsk_test_fake_key_for_tests"
os.environ["GROQ_API_KEY_2"] = ""
os.environ["RECRUITER_DEFAULT_PASSWORD"] = "TestPassword123!"
os.environ["ENVIRONMENT"] = "test"
os.environ["STRICT_DEPLOYMENT_CONFIG"] = "0"


@pytest.fixture(autouse=True)
def _fresh_database():
    """Create fresh tables before each test, drop them after."""
    from database import Base, engine, init_db

    Base.metadata.create_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a clean DB session for tests that need direct queries."""
    from database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_scores():
    """Well-formed LLM dimension scores for testing."""
    return {
        "clarity": 8,
        "relevance": 7,
        "star_quality": 6,
        "specificity": 7,
        "communication": 8,
        "job_fit": 7,
        "summary": "Solid answer with good examples.",
        "star_detected": True,
        "key_strength": "Clear communication",
        "key_improvement": "More specific metrics",
        "recruiter_verdict": "Advance",
        "star_components": {
            "situation": True,
            "task": True,
            "action": True,
            "result": False,
        },
    }


@pytest.fixture
def empty_scores():
    """Zero scores — as returned by _empty_scores()."""
    return {
        "clarity": 0,
        "relevance": 0,
        "star_quality": 0,
        "specificity": 0,
        "communication": 0,
        "job_fit": 0,
        "summary": "No answer provided.",
        "star_detected": False,
        "key_strength": "N/A",
        "key_improvement": "Provide a complete answer",
        "recruiter_verdict": "Do Not Advance",
        "star_components": {
            "situation": False,
            "task": False,
            "action": False,
            "result": False,
        },
    }


@pytest.fixture
def test_org_id():
    """Create a test organization and return its org_id."""
    from saas.saas_db import init_saas_db, create_organization

    init_saas_db()
    org_id = create_organization("Test Corp", "test@testcorp.com")
    return org_id
