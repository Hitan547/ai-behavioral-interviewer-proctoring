"""
tests/test_database.py
----------------------
Tests for database CRUD operations: auth, sessions, job postings, candidates.
"""

import pytest
from database import (
    register_student, verify_login, save_session, get_all_sessions,
    save_job_posting, get_job_posting_by_id, get_all_job_postings,
    save_candidate_profile, create_candidate_account,
    get_candidates_by_jd, update_interview_status,
    get_sessions_by_org, get_session_by_id,
    update_candidate_status, save_recruiter_notes,
)


# ── Authentication ───────────────────────────────────────────────────────


class TestAuth:
    def test_register_student_success(self):
        ok, msg = register_student("testuser1", "password123", "Test User", "test@example.com")
        assert ok is True
        assert "created" in msg.lower()

    def test_register_duplicate_username(self):
        register_student("dupuser", "password123")
        ok, msg = register_student("dupuser", "password456")
        assert ok is False
        assert "taken" in msg.lower()

    def test_register_short_password(self):
        ok, msg = register_student("shortpw", "12345")
        assert ok is False
        assert "6 characters" in msg

    def test_verify_login_success(self):
        register_student("logintest", "mypassword", "Login Test")
        user = verify_login("logintest", "mypassword")
        assert user is not None
        assert user["username"] == "logintest"
        assert user["role"] == "student"

    def test_verify_login_wrong_password(self):
        register_student("wrongpw", "correctpass")
        user = verify_login("wrongpw", "wrongpass")
        assert user is None

    def test_verify_login_nonexistent(self):
        user = verify_login("noexist", "whatever")
        assert user is None

    def test_verify_login_email_path(self):
        register_student("emaillogin", "pass123456", "User", "user@test.com")
        user = verify_login("user@test.com", "pass123456")
        assert user is not None
        assert user["username"] == "emaillogin"

    def test_default_recruiter_exists(self):
        """init_db seeds a default recruiter account."""
        user = verify_login("recruiter", "TestPassword123!")
        assert user is not None
        assert user["role"] == "recruiter"


# ── Session CRUD ─────────────────────────────────────────────────────────


class TestSessions:
    def test_save_and_retrieve_session(self):
        register_student("candidate1", "pass123456", "Candidate One")
        session_id = save_session(
            candidate_name="Candidate One",
            username="candidate1",
            final_score=75.5,
            cognitive_score=80.0,
            emotion_score=70.0,
            engagement_score=72.0,
            questions_answered=5,
        )
        assert session_id > 0

        sessions = get_all_sessions()
        assert len(sessions) >= 1
        assert sessions[0].candidate_name == "Candidate One"
        assert sessions[0].final_score == 75.5

    def test_session_with_proctoring_data(self):
        register_student("proctor1", "pass123456")
        proctoring = {
            "risk_level": "Medium",
            "tab_switch_count": 3,
            "risk_score": 15,
        }
        session_id = save_session(
            candidate_name="Proctor Test",
            username="proctor1",
            final_score=60.0,
            cognitive_score=65.0,
            emotion_score=55.0,
            engagement_score=60.0,
            questions_answered=5,
            proctoring_data=proctoring,
        )
        session = get_session_by_id(session_id)
        assert session.proctoring_risk == "Medium"
        assert session.tab_switch_count == 3

    def test_update_candidate_status(self):
        register_student("statustest", "pass123456")
        sid = save_session(
            candidate_name="Status", username="statustest",
            final_score=70, cognitive_score=70,
            emotion_score=70, engagement_score=70,
            questions_answered=5,
        )
        update_candidate_status(sid, "Hired")
        session = get_session_by_id(sid)
        assert session.status == "Hired"

    def test_save_recruiter_notes(self):
        register_student("notetest", "pass123456")
        sid = save_session(
            candidate_name="Notes", username="notetest",
            final_score=70, cognitive_score=70,
            emotion_score=70, engagement_score=70,
            questions_answered=5,
        )
        save_recruiter_notes(sid, "Great candidate, strong communication skills")
        session = get_session_by_id(sid)
        assert "strong communication" in session.recruiter_notes


# ── Job Postings ─────────────────────────────────────────────────────────


class TestJobPostings:
    def test_create_and_retrieve(self):
        jd_id = save_job_posting(
            title="Senior Python Developer",
            jd_text="We need a Python developer with 5+ years...",
            min_pass_score=70,
        )
        assert jd_id > 0

        posting = get_job_posting_by_id(jd_id)
        assert posting.title == "Senior Python Developer"
        assert posting.min_pass_score == 70
        assert posting.status == "Active"

    def test_list_postings(self):
        save_job_posting(title="Job A", jd_text="A desc")
        save_job_posting(title="Job B", jd_text="B desc")
        postings = get_all_job_postings()
        assert len(postings) >= 2


# ── Candidate Profiles ──────────────────────────────────────────────────


class TestCandidateProfiles:
    def test_save_profile(self):
        jd_id = save_job_posting(title="ML Engineer", jd_text="ML role")
        profile_id = save_candidate_profile(
            name="Alice Smith",
            email="alice@example.com",
            jd_id=jd_id,
            resume_text="Python, TensorFlow, 3 years...",
            match_score=8.5,
            match_reason="Strong ML background",
        )
        assert profile_id > 0

    def test_create_candidate_account(self):
        jd_id = save_job_posting(title="Backend Dev", jd_text="Backend role")
        profile_id = save_candidate_profile(
            name="Bob Jones",
            email="bob@example.com",
            jd_id=jd_id,
        )
        result = create_candidate_account(profile_id)
        assert "username" in result
        assert "password" in result
        assert len(result["password"]) >= 8

    def test_create_account_idempotent(self):
        """Calling create_candidate_account twice should not error."""
        jd_id = save_job_posting(title="DevOps", jd_text="DevOps role")
        pid = save_candidate_profile(name="Carol", email="carol@ex.com", jd_id=jd_id)
        r1 = create_candidate_account(pid)
        r2 = create_candidate_account(pid)
        assert r1["username"] == r2["username"]

    def test_candidates_by_jd(self):
        jd_id = save_job_posting(title="Test JD", jd_text="Test")
        save_candidate_profile(name="A", email="a@x.com", jd_id=jd_id, match_score=7)
        save_candidate_profile(name="B", email="b@x.com", jd_id=jd_id, match_score=9)
        candidates = get_candidates_by_jd(jd_id)
        assert len(candidates) == 2
        # Should be ordered by match_score desc
        assert candidates[0].match_score >= candidates[1].match_score

    def test_interview_status_update(self):
        jd_id = save_job_posting(title="Status JD", jd_text="Test")
        pid = save_candidate_profile(name="Dan", email="dan@x.com", jd_id=jd_id)
        result = create_candidate_account(pid)
        update_interview_status(result["username"], jd_id, "In Progress")
        candidates = get_candidates_by_jd(jd_id)
        assert candidates[0].interview_status == "In Progress"


# ── Session with JD linking ──────────────────────────────────────────────


class TestSessionJDLinking:
    def test_session_auto_pass_threshold(self):
        """Sessions linked to a JD should auto-update candidate status."""
        jd_id = save_job_posting(title="Auto Pass Test", jd_text="Test", min_pass_score=60)
        pid = save_candidate_profile(name="Eve", email="eve@x.com", jd_id=jd_id)
        creds = create_candidate_account(pid)

        # Score above threshold → Passed
        save_session(
            candidate_name="Eve", username=creds["username"],
            final_score=75, cognitive_score=80,
            emotion_score=70, engagement_score=75,
            questions_answered=5, jd_id=jd_id,
        )
        candidates = get_candidates_by_jd(jd_id)
        assert candidates[0].interview_status == "Passed"

    def test_session_below_threshold(self):
        jd_id = save_job_posting(title="Below Test", jd_text="Test", min_pass_score=70)
        pid = save_candidate_profile(name="Frank", email="frank@x.com", jd_id=jd_id)
        creds = create_candidate_account(pid)

        save_session(
            candidate_name="Frank", username=creds["username"],
            final_score=55, cognitive_score=50,
            emotion_score=60, engagement_score=55,
            questions_answered=5, jd_id=jd_id,
        )
        candidates = get_candidates_by_jd(jd_id)
        assert candidates[0].interview_status == "Below Threshold"
