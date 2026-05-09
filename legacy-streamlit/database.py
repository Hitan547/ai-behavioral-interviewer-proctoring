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
    DateTime, Boolean, Text, ForeignKey, func, or_, text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os, json, hashlib, random, string
import bcrypt

# Keep the default DB path consistent with .env and manual Streamlit runs.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./psysense.db")
_IS_SQLITE = DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    _db_path = DATABASE_URL.replace("sqlite:///", "")
    _db_dir  = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

# Connection pool tuning for PostgreSQL; SQLite needs check_same_thread=False.
_engine_kwargs: dict = {}
if _IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update({
        "pool_size":        int(os.getenv("DATABASE_POOL_SIZE", "5")),
        "max_overflow":     int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
        "pool_pre_ping":    True,   # auto-reconnect stale connections
        "pool_recycle":     1800,   # recycle connections every 30 min
    })

engine = create_engine(DATABASE_URL, **_engine_kwargs)
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
    org_id         = Column(String,   nullable=True)

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
    questions_json   = Column(Text,     nullable=True)       # JSON list
    keywords_json    = Column(Text,     nullable=True)       # JSON list of lists
    vocab_json       = Column(Text,     nullable=True)       # JSON dict
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

    # Anti-cheating proctoring data
    proctoring_json  = Column(Text,    nullable=True)     # Full event log JSON
    proctoring_risk  = Column(String,  default="Low")     # Low / Medium / High
    tab_switch_count = Column(Integer, default=0)


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

def _get_existing_columns(db, table_name: str) -> set:
    """Return column names for a table. Works on SQLite and PostgreSQL."""
    if _IS_SQLITE:
        rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return {row[1] for row in rows}
    else:
        # PostgreSQL: use information_schema
        rows = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :tbl"
        ), {"tbl": table_name}).fetchall()
        return {row[0] for row in rows}


def _safe_add_column(db, table_name: str, col_name: str, col_type: str = "TEXT"):
    """Add a column if it doesn't exist. Works on SQLite and PostgreSQL."""
    existing = _get_existing_columns(db, table_name)
    if col_name not in existing:
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
        db.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ── Schema migrations (both SQLite and PostgreSQL) ──
        _safe_add_column(db, "job_postings", "org_id", "VARCHAR")
        for col_name in ("questions_json", "keywords_json", "vocab_json"):
            _safe_add_column(db, "candidate_profiles", col_name, "TEXT")

        # ── Backfill orphaned postings with org_id ──
        orphaned_postings = db.query(JobPosting).filter(
            JobPosting.org_id.is_(None),
            JobPosting.recruiter_email.isnot(None),
        ).all()
        for posting in orphaned_postings:
            owner = db.query(User).filter(
                func.lower(User.email) == (posting.recruiter_email or "").casefold(),
                User.role == "recruiter",
                User.org_id.isnot(None),
            ).first()
            if owner:
                posting.org_id = owner.org_id
        if orphaned_postings:
            db.commit()

        # ── Seed default recruiter account ──
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
    # Be tolerant of copy-pasted credentials from email/chat clients.
    def _clean_cred(value: str) -> str:
        v = (value or "")
        for ch in ("\u200b", "\ufeff", "\xa0"):
            v = v.replace(ch, "")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'", "`"):
            v = v[1:-1].strip()
        return v

    username = _clean_cred(username)
    password = _clean_cred(password)
    if not username or not password:
        return None

    db = SessionLocal()
    try:
        # Accept username or email (case-insensitive).
        username_lc = username.casefold()
        user = (
            db.query(User)
            .filter(func.lower(User.username) == username_lc)
            .order_by(User.id.desc())
            .first()
        )

        def _auth_ok(u: User) -> bool:
            if _verify_hash(password, u.password_hash):
                return True
            # Fallback: SHA256 for any accounts created before bcrypt migration
            import hashlib
            return hashlib.sha256(password.encode()).hexdigest() == u.password_hash

        if user:
            # If a username was provided, authenticate against that exact account only.
            if _auth_ok(user):
                return {
                    "id":           user.id,
                    "username":     user.username,
                    "role":         user.role,
                    "display_name": user.display_name or user.username,
                    "email":        user.email,
                    "org_id":       user.org_id,
                }
            return None

        # Email login path: multiple accounts can share the same email.
        candidates = db.query(User).filter(func.lower(User.email) == username_lc).all()
        if not candidates:
            return None

        # Prefer recruiter when several accounts share one email.
        ordered = sorted(candidates, key=lambda u: 0 if u.role == "recruiter" else 1)
        for u in ordered:
            if _auth_ok(u):
                return {
                    "id":           u.id,
                    "username":     u.username,
                    "role":         u.role,
                    "display_name": u.display_name or u.username,
                    "email":        u.email,
                    "org_id":       u.org_id,
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
    proctoring_data:    dict = None,   # V3 — anti-cheating proctoring summary
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
            proctoring_json         = json.dumps(proctoring_data)    if proctoring_data    else None,
            proctoring_risk         = (proctoring_data or {}).get("risk_level", "Low"),
            tab_switch_count        = (proctoring_data or {}).get("tab_switch_count", 0),
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


def get_sessions_by_org(org_id: str = None):
    """Return sessions filtered by org_id via User table.
    Falls back to all sessions if org_id is None."""
    init_db()
    db = SessionLocal()
    try:
        q = db.query(CandidateSession)
        if org_id:
            org_usernames = [
                u.username for u in db.query(User.username)
                .filter(User.org_id == org_id).all()
            ]
            org_job_ids = [
                p.id for p in db.query(JobPosting.id)
                .filter(JobPosting.org_id == org_id).all()
            ]
            filters = []
            if org_usernames:
                filters.append(CandidateSession.username.in_(org_usernames))
            if org_job_ids:
                filters.append(CandidateSession.jd_id.in_(org_job_ids))
            q = q.filter(or_(*filters)) if filters else q.filter(False)
        return q.order_by(CandidateSession.created_at.desc()).all()
    finally:
        db.close()


def get_session_by_id_for_org(session_id: int, org_id: str = None):
    """Return one session only if it belongs to the supplied org."""
    if not org_id:
        return get_session_by_id(session_id)
    init_db()
    db = SessionLocal()
    try:
        rec = db.query(CandidateSession).filter(CandidateSession.id == session_id).first()
        if not rec:
            return None
        if rec.username:
            user = db.query(User).filter(User.username == rec.username).first()
            if user and user.org_id == org_id:
                return rec
        if rec.jd_id:
            posting = db.query(JobPosting).filter(JobPosting.id == rec.jd_id).first()
            if posting and posting.org_id == org_id:
                return rec
        return None
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
    org_id:         str       = None,
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
            org_id         = org_id,
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


def get_job_postings_by_org(org_id: str = None):
    """Return job postings visible to one recruiter org."""
    init_db()
    db = SessionLocal()
    try:
        q = db.query(JobPosting)
        if org_id:
            q = q.filter(JobPosting.org_id == org_id)
        return q.order_by(JobPosting.created_at.desc()).all()
    finally:
        db.close()


def get_job_posting_by_id(jd_id: int):
    db = SessionLocal()
    try:
        return db.query(JobPosting).filter(JobPosting.id == jd_id).first()
    finally:
        db.close()


def get_job_posting_by_id_for_org(jd_id: int, org_id: str = None):
    if not org_id:
        return get_job_posting_by_id(jd_id)
    db = SessionLocal()
    try:
        return db.query(JobPosting).filter(
            JobPosting.id == jd_id,
            JobPosting.org_id == org_id,
        ).first()
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

def close_job_posting_for_org(jd_id: int, org_id: str = None):
    db = SessionLocal()
    try:
        q = db.query(JobPosting).filter(JobPosting.id == jd_id)
        if org_id:
            q = q.filter(JobPosting.org_id == org_id)
        posting = q.first()
        if posting:
            posting.status = "Closed"
            db.commit()
    finally:
        db.close()


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
    questions:       list  = None,
    keywords:        list  = None,
    vocab:           dict  = None,
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
            questions_json   = json.dumps(questions or []),
            keywords_json    = json.dumps(keywords or []),
            vocab_json       = json.dumps(vocab or {}),
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

        posting = db.query(JobPosting).filter(JobPosting.id == profile.jd_id).first()
        profile_org_id = posting.org_id if posting else None

        if profile.account_created:
            # Re-invite path: return existing credentials when available.
            # If the temp password was cleared, rotate to a fresh one.
            existing_password = profile.temp_password
            if not existing_password:
                existing_password = _random_password(8)
                user = db.query(User).filter(User.username == profile.username).first()
                if not user:
                    return {"error": "User not found for existing profile"}
                user.password_hash = _hash(existing_password)
                if profile_org_id:
                    user.org_id = profile_org_id
                profile.temp_password = existing_password
                db.commit()
            elif profile_org_id:
                user = db.query(User).filter(User.username == profile.username).first()
                if user and user.org_id != profile_org_id:
                    user.org_id = profile_org_id
                    db.commit()

            return {
                "username": profile.username,
                "password": existing_password,
                "already_existed": True,
            }

        # Always generate a fresh, unique username + password per candidate.
        # Each person who receives an invite gets their own distinct credentials.
        password = _random_password(10)
        username = _generate_username(profile.name)

        # Check if this exact username already exists (edge case from prior run)
        existing_user = db.query(User).filter_by(username=username).first()
        if existing_user:
            # Rotate password on the existing account
            existing_user.password_hash = _hash(password)
            if profile.name:
                existing_user.display_name = profile.name
        else:
            db.add(User(
                username      = username,
                password_hash = _hash(password),
                role          = "student",
                display_name  = profile.name,
                email         = profile.email,
                org_id        = profile_org_id,
            ))
        if existing_user and profile_org_id:
            existing_user.org_id = profile_org_id

        # Update profile
        profile.username        = username
        profile.temp_password   = password          # stored plain for email send
        profile.account_created = True
        profile.interview_status = "Invited"

        db.commit()
        return {
            "username": username,
            "password": password,
        }
    finally:
        db.close()


def mark_invite_sent(profile_id: int):
    """Call after n8n email webhook fires successfully.

    Also clears temp_password — the candidate received it via email,
    so there's no reason to keep plaintext credentials in the DB.
    """
    db = SessionLocal()
    try:
        profile = db.query(CandidateProfile).filter(
            CandidateProfile.id == profile_id
        ).first()
        if profile:
            profile.invite_sent_at = datetime.utcnow()
            profile.temp_password = None   # security: clear plaintext password
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


def get_profile_for_candidate(username: str = "", email: str = ""):
    """Get an invited candidate profile by username, with email fallback.

    Username is the primary link. Email fallback helps older/manual student
    accounts reach their latest invited profile during local testing.
    """
    db = SessionLocal()
    try:
        username = (username or "").strip()
        email = (email or "").strip()
        if username:
            profile = db.query(CandidateProfile).filter(
                CandidateProfile.username == username
            ).order_by(CandidateProfile.id.desc()).first()
            if profile:
                return profile
        if email:
            return db.query(CandidateProfile).filter(
                func.lower(CandidateProfile.email) == email.casefold(),
                CandidateProfile.resume_text.isnot(None),
            ).order_by(CandidateProfile.id.desc()).first()
        return None
    finally:
        db.close()


def save_candidate_questions(profile_id: int, questions: list, keywords: list = None, vocab: dict = None):
    """Persist prepared interview questions for an invited candidate."""
    db = SessionLocal()
    try:
        profile = db.query(CandidateProfile).filter(CandidateProfile.id == profile_id).first()
        if profile:
            profile.questions_json = json.dumps(questions or [])
            profile.keywords_json = json.dumps(keywords or [])
            profile.vocab_json = json.dumps(vocab or {})
            db.commit()
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
