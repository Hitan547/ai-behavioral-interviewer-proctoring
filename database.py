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
"""

from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    DateTime, Boolean, Text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os, json, hashlib

os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite:///data/psysense.db"
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    created_at    = Column(DateTime, default=datetime.utcnow)


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
    status          = Column(String,  default="Pending")
    recruiter_notes = Column(Text,    nullable=True)


# ── Private helper ────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── Init ──────────────────────────────────────────────────────────────────

def init_db():
    """Create tables and seed the default recruiter account."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="recruiter").first():
            db.add(User(
                username="recruiter",
                password_hash=_hash("admin123"),
                role="recruiter",
                display_name="Recruiter",
            ))
            db.commit()
    finally:
        db.close()


# ── Auth ──────────────────────────────────────────────────────────────────

def verify_login(username: str, password: str):
    """Return user dict on success, None on failure."""
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(
            username=username, password_hash=_hash(password)
        ).first()
        if user:
            return {
                "id":           user.id,
                "username":     user.username,
                "role":         user.role,
                "display_name": user.display_name or user.username,
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
            status                  = "Pending",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
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