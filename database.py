from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite:///data/psysense.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class CandidateSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Final fused score
    final_score = Column(Float)

    # Per-signal breakdown
    cognitive_score = Column(Float)
    emotion_score = Column(Float)
    engagement_score = Column(Float)

    # Number of questions answered
    questions_answered = Column(Integer, default=0)

    # Flag: True if final_score < 50
    flagged = Column(Boolean, default=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def save_session(
    candidate_name: str,
    final_score: float,
    cognitive_score: float,
    emotion_score: float,
    engagement_score: float,
    questions_answered: int
):
    init_db()
    db = SessionLocal()
    try:
        flagged = final_score < 50
        session = CandidateSession(
            candidate_name=candidate_name,
            final_score=round(final_score, 1),
            cognitive_score=round(cognitive_score, 1),
            emotion_score=round(emotion_score, 1),
            engagement_score=round(engagement_score, 1),
            questions_answered=questions_answered,
            flagged=flagged
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id
    finally:
        db.close()


def get_all_sessions():
    init_db()
    db = SessionLocal()
    try:
        return db.query(CandidateSession).order_by(CandidateSession.created_at.desc()).all()
    finally:
        db.close()


def get_session_by_id(session_id: int):
    init_db()
    db = SessionLocal()
    try:
        return db.query(CandidateSession).filter(CandidateSession.id == session_id).first()
    finally:
        db.close()