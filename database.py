"""
database.py
-----------
Pure data layer for PsySense. No Streamlit imports.

Root cause of previous NameError:
  The content of pages/dashboard.py (st.set_page_config, st.session_state
  auth guard, etc.) was accidentally pasted into this file after the
  verify_login function. Since 'st' is not imported here, every import
  of database.py exploded with NameError: name 'st' is not defined.
  Removed. This file must never import streamlit.

V2 additions:
  - JobPosting table
  - CandidateProfile table
  - jd_id column on CandidateSession
  - create_candidate_account()
  - update_interview_status()
  - get_candidates_by_jd()
  - get_all_job_postings()
  - get_job_posting_by_id()
  - save_job_posting()
  - check_expired_invites()
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os, json, hashlib, random, string
import bcrypt

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/psysense.db")

if DATABASE_URL.startswith("sqlite:///"):
    _db_path = DATABASE_URL.replace("sqlite:///", "")
    _db_dir  = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()
# ── Models ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer,  primary_key=True, autoincrement=True)
    username      = Column(String,   unique=True, nullable=False)
    password_hash = Column(String,   nullable=False)
    role          = Column(String,   default="student")
    display_name  = Column(String,   nullable=True)
    email         = Column(String,   nullable=True)
    org_id        = Column(String,   nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


class JobPosting(Base):
    """One row per job the recruiter creates."""
    __tablename__ = "job_postings"
    id             = Column(Integer,  primary_key=True, autoincrement=True)
    title          = Column(String,   nullable=False)
    jd_text        = Column(Text,     nullable=False)
    min_pass_score = Column(Integer,  default=60)          # out of 100
    deadline       = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    status         = Column(String,   default="Active")    # Active / Closed
    recruiter_email = Column(String,  nullable=True) 

class CandidateProfile(Base):
    """
    One row per candidate per job posting.
    Created during the matching / invite phase — before the interview.
    """
    __tablename__ = "candidate_profiles"
    id               = Column(Integer,  primary_key=True, autoincrement=True)
    name             = Column(String,   nullable=False)
    email            = Column(String,   nullable=False)
    resume_text      = Column(Text,     nullable=True)
    resume_filename  = Column(String,   nullable=True)
    jd_id            = Column(Integer,  ForeignKey("job_postings.id"), nullable=False)
    match_score      = Column(Float,    nullable=True)       # 0-10 from LLM
    match_reason     = Column(Text,     nullable=True)
    key_matches      = Column(Text,     nullable=True)       # JSON list
    key_gaps         = Column(Text,     nullable=True)       # JSON list
    username         = Column(String,   nullable=True)       # auto-generated
    temp_password    = Column(String,   nullable=True)       # shown once to recruiter
    account_created  = Column(Boolean,  default=False)
    invite_sent_at   = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    # Invited / In Progress / Completed / Passed / Below Threshold / Expired
    interview_status = Column(String, default="Shortlisted")


class CandidateSession(Base):
    __tablename__ = "sessions"
    id              = Column(Integer,  primary_key=True, autoincrement=True)
    candidate_name  = Column(String,   nullable=False)
    username        = Column(String,   nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    final_score        = Column(Float)
    cognitive_score    = Column(Float)
    emotion_score      = Column(Float)
    engagement_score   = Column(Float)
    questions_answered = Column(Integer, default=0)
    flagged            = Column(Boolean, default=False)

    insight_json            = Column(Text, nullable=True)
    per_question_json       = Column(Text, nullable=True)
    recruiter_verdicts_json = Column(Text, nullable=True)

    jd_used         = Column(Boolean, default=False)
    jd_id           = Column(Integer, ForeignKey("job_postings.id"), nullable=True)  # V2
    status          = Column(String,  default="Pending")
    recruiter_notes = Column(Text,    nullable=True)


# ── Private helpers ───────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    """Hash a password with bcrypt. Returns a string."""
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def _verify_hash(pw: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def _random_password(length: int = 8) -> str:
    """Generate a random alphanumeric password."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def _generate_username(name: str) -> str:
    """
    firstname + 4 random digits, lowercased.
    Guaranteed unique — retries if username already exists in DB.
    """
    first = name.strip().split()[0].lower()
    # strip non-alpha chars
    first = "".join(c for c in first if c.isalpha())
    db = SessionLocal()
    try:
        for _ in range(10):
            candidate = first + "".join(random.choices(string.digits, k=4))
            if not db.query(User).filter_by(username=candidate).first():
                return candidate
        # fallback — full random
        return "user" + "".join(random.choices(string.digits, k=6))
    finally:
        db.close()


# ── Init ──────────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="recruiter").first():
            _default_pw = os.getenv("RECRUITER_DEFAULT_PASSWORD", "admin123")
            db.add(User(
                username="recruiter",
                password_hash=_hash(_default_pw),
                role="recruiter",
                display_name="Recruiter",
            ))
            db.commit()
    finally:
        db.close()


# ── Auth ──────────────────────────────────────────────────────────────────

def verify_login(username: str, password: str):
    db = SessionLocal()
    try:
        # Accept email OR username
        user = db.query(User).filter_by(username=username).first()
        if not user:
            user = db.query(User).filter_by(email=username).first()
        if not user:
            return None

        # bcrypt check
        if _verify_hash(password, user.password_hash):
            return {
                "id":           user.id,
                "username":     user.username,
                "role":         user.role,
                "display_name": user.display_name or user.username,
                "email":        user.email,
            }

        # Fallback: SHA256 for any accounts created before bcrypt migration
        import hashlib
        if hashlib.sha256(password.encode()).hexdigest() == user.password_hash:
            return {
                "id":           user.id,
                "username":     user.username,
                "role":         user.role,
                "display_name": user.display_name or user.username,
                "email":        user.email,
            }

        return None
    finally:
        db.close()


def register_student(username: str, password: str, display_name: str = "", email: str = ""):
    """Create a new student account. Returns (success, message)."""
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    db = SessionLocal()
    try:
        if db.query(User).filter_by(username=username).first():
            return False, "Username already taken — try another."
        db.add(User(
            username=username,
            password_hash=_hash(password),
            role="student",
            display_name=display_name or username,
            email=email or None,
        ))
        db.commit()
        return True, "Account created! You can now log in."
    finally:
        db.close()


# ── Session CRUD ──────────────────────────────────────────────────────────

def save_session(
    candidate_name:     str,
    username:           str,
    final_score:        float,
    cognitive_score:    float,
    emotion_score:      float,
    engagement_score:   float,
    questions_answered: int,
    insight_data:       dict = None,
    per_question_data:  list = None,
    jd_used:            bool = False,
    recruiter_verdicts: list = None,
    jd_id:              int  = None,   # V2 — pass if interview was JD-linked
) -> int:
    init_db()
    db = SessionLocal()
    try:
        rec = CandidateSession(
            candidate_name          = candidate_name,
            username                = username,
            final_score             = round(final_score,      1),
            cognitive_score         = round(cognitive_score,  1),
            emotion_score           = round(emotion_score,    1),
            engagement_score        = round(engagement_score, 1),
            questions_answered      = questions_answered,
            flagged                 = final_score < 50,
            insight_json            = json.dumps(insight_data)       if insight_data       else None,
            per_question_json       = json.dumps(per_question_data)  if per_question_data  else None,
            recruiter_verdicts_json = json.dumps(recruiter_verdicts) if recruiter_verdicts else None,
            jd_used                 = jd_used,
            jd_id                   = jd_id,
            status                  = "Pending",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        # ── V2: threshold check ───────────────────────────────────────────
        if jd_id:
            posting = db.query(JobPosting).filter(JobPosting.id == jd_id).first()
            if posting:
                passed = final_score >= posting.min_pass_score
                new_status = "Passed" if passed else "Below Threshold"
                update_interview_status(username, jd_id, new_status)

        return rec.id
    finally:
        db.close()


def get_all_sessions():
    init_db()
    db = SessionLocal()
    try:
        return db.query(CandidateSession).order_by(
            CandidateSession.created_at.desc()
        ).all()
    finally:
        db.close()


def get_session_by_id(session_id: int):
    db = SessionLocal()
    try:
        return db.query(CandidateSession).filter(
            CandidateSession.id == session_id
        ).first()
    finally:
        db.close()


def get_sessions_by_username(username: str):
    db = SessionLocal()
    try:
        return db.query(CandidateSession).filter_by(username=username).order_by(
            CandidateSession.created_at.desc()
        ).all()
    finally:
        db.close()


def update_candidate_status(session_id: int, status: str):
    db = SessionLocal()
    try:
        rec = db.query(CandidateSession).filter(CandidateSession.id == session_id).first()
        if rec:
            rec.status = status
            db.commit()
    finally:
        db.close()


def save_recruiter_notes(session_id: int, notes: str):
    db = SessionLocal()
    try:
        rec = db.query(CandidateSession).filter(CandidateSession.id == session_id).first()
        if rec:
            rec.recruiter_notes = notes
            db.commit()
    finally:
        db.close()


def get_all_users():
    db = SessionLocal()
    try:
        return db.query(User).filter(User.role == "student").order_by(
            User.created_at.desc()
        ).all()
    finally:
        db.close()


# ── V2: Job Posting CRUD ──────────────────────────────────────────────────

def save_job_posting(
    title:          str,
    jd_text:        str,
    min_pass_score: int      = 60,
    deadline:       datetime = None,
    recruiter_email: str      = None,
) -> int:
    """Create a new job posting. Returns the new posting id."""
    init_db()
    db = SessionLocal()
    try:
        posting = JobPosting(
            title          = title,
            jd_text        = jd_text,
            min_pass_score = min_pass_score,
            deadline       = deadline,
            status         = "Active",
            recruiter_email = recruiter_email,
        )
        db.add(posting)
        db.commit()
        db.refresh(posting)
        return posting.id
    finally:
        db.close()


def get_all_job_postings():
    """Return all job postings ordered by newest first."""
    init_db()
    db = SessionLocal()
    try:
        return db.query(JobPosting).order_by(JobPosting.created_at.desc()).all()
    finally:
        db.close()


def get_job_posting_by_id(jd_id: int):
    db = SessionLocal()
    try:
        return db.query(JobPosting).filter(JobPosting.id == jd_id).first()
    finally:
        db.close()


def close_job_posting(jd_id: int):
    db = SessionLocal()
    try:
        posting = db.query(JobPosting).filter(JobPosting.id == jd_id).first()
        if posting:
            posting.status = "Closed"
            db.commit()
    finally:
        db.close()


# ── V2: Candidate Profile CRUD ────────────────────────────────────────────

def save_candidate_profile(
    name:            str,
    email:           str,
    jd_id:           int,
    resume_text:     str   = "",
    resume_filename: str   = "",
    match_score:     float = None,
    match_reason:    str   = "",
    key_matches:     list  = None,
    key_gaps:        list  = None,
) -> int:
    """Save a matched candidate before account creation. Returns profile id."""
    init_db()
    db = SessionLocal()
    try:
        profile = CandidateProfile(
            name            = name,
            email           = email,
            jd_id           = jd_id,
            resume_text     = resume_text,
            resume_filename = resume_filename,
            match_score     = match_score,
            match_reason    = match_reason,
            key_matches     = json.dumps(key_matches or []),
            key_gaps        = json.dumps(key_gaps    or []),
            interview_status = "Shortlisted",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile.id
    finally:
        db.close()


def create_candidate_account(profile_id: int) -> dict:
    """
    Auto-create a student login account for a shortlisted candidate.
    Returns {username, password} — password shown once, then only hash stored.
    Safe to call multiple times — skips if account already created.
    """
    db = SessionLocal()
    try:
        profile = db.query(CandidateProfile).filter(
            CandidateProfile.id == profile_id
        ).first()

        if not profile:
            return {"error": "Profile not found"}

        if profile.account_created:
            return {"username": profile.username, "already_existed": True}

        username = _generate_username(profile.name)
        password = _random_password(8)

        # Create Users entry
        db.add(User(
            username      = username,
            password_hash = _hash(password),
            role          = "student",
            display_name  = profile.name,
            email         = profile.email,
        ))

        # Update profile
        profile.username        = username
        profile.temp_password   = password          # stored plain for email send
        profile.account_created = True
        profile.interview_status = "Invited"

        db.commit()
        return {"username": username, "password": password}
    finally:
        db.close()


def mark_invite_sent(profile_id: int):
    """Call after n8n email webhook fires successfully."""
    db = SessionLocal()
    try:
        profile = db.query(CandidateProfile).filter(
            CandidateProfile.id == profile_id
        ).first()
        if profile:
            profile.invite_sent_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def update_interview_status(username: str, jd_id: int, status: str):
    """
    Update CandidateProfile.interview_status for a given username + jd.
    Called at: interview start (In Progress), completion (Completed/Passed/Below Threshold).
    """
    db = SessionLocal()
    try:
        profile = db.query(CandidateProfile).filter(
            CandidateProfile.username == username,
            CandidateProfile.jd_id   == jd_id,
        ).first()
        if profile:
            profile.interview_status = status
            db.commit()
    finally:
        db.close()


def get_candidates_by_jd(jd_id: int):
    """Return all CandidateProfiles for a job posting, ranked by match_score."""
    init_db()
    db = SessionLocal()
    try:
        return (
            db.query(CandidateProfile)
            .filter(CandidateProfile.jd_id == jd_id)
            .order_by(CandidateProfile.match_score.desc())
            .all()
        )
    finally:
        db.close()


def get_profile_by_username(username: str):
    """Get CandidateProfile for a logged-in student (to load their jd_id)."""
    db = SessionLocal()
    try:
        return db.query(CandidateProfile).filter(
            CandidateProfile.username == username
        ).first()
    finally:
        db.close()


def check_expired_invites():
    """
    Mark any Invited/In Progress candidates as Expired if deadline has passed.
    Call this on recruiter dashboard load.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        # Get all active postings with a deadline
        postings = db.query(JobPosting).filter(
            JobPosting.status   == "Active",
            JobPosting.deadline != None,
        ).all()

        for posting in postings:
            if posting.deadline < now:
                expired = db.query(CandidateProfile).filter(
                    CandidateProfile.jd_id           == posting.id,
                    CandidateProfile.interview_status.in_(["Invited", "In Progress"]),
                ).all()
                for profile in expired:
                    profile.interview_status = "Expired"

        db.commit()
    finally:
        db.close()


def get_jd_stats(jd_id: int) -> dict:
    """
    Return counts of each interview_status for a job posting.
    Used in recruiter dashboard stats row.
    """
    db = SessionLocal()
    try:
        profiles = db.query(CandidateProfile).filter(
            CandidateProfile.jd_id == jd_id
        ).all()

        stats = {
            "total":           len(profiles),
            "Shortlisted":     0,
            "Invited":         0,
            "In Progress":     0,
            "Completed":       0,
            "Passed":          0,
            "Below Threshold": 0,
            "Expired":         0,
        }
        for p in profiles:
            if p.interview_status in stats:
                stats[p.interview_status] += 1

        return stats
    finally:
        db.close()