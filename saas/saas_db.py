"""
saas_db.py
----------
SaaS-specific database layer — organizations, subscriptions, usage tracking.
Designed to work alongside existing database.py (no modifications needed to existing functions).
"""

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import uuid, os, json

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
Base = declarative_base()


# ── SaaS Models ───────────────────────────────────────────────────────────

class Organization(Base):
    """One row per customer company/team."""
    __tablename__ = "organizations"
    
    org_id                 = Column(String, primary_key=True)
    org_name               = Column(String, nullable=False)
    owner_email            = Column(String, unique=True, nullable=False)
    subscription_plan      = Column(String, default="trial")  # trial, starter, pro, enterprise
    stripe_customer_id     = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    api_key                = Column(String, unique=True, nullable=True)
    
    max_interviews_per_month = Column(Integer, default=50)
    used_interviews          = Column(Integer, default=0)
    current_month            = Column(String, nullable=True)  # YYYY-MM
    
    active                = Column(Integer, default=1)
    trial_started_at      = Column(DateTime, default=datetime.utcnow)
    trial_expires_at      = Column(DateTime, nullable=True)
    created_at            = Column(DateTime, default=datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.utcnow)


class SubscriptionLog(Base):
    """Audit trail for billing events."""
    __tablename__ = "subscription_logs"
    
    id             = Column(Integer, primary_key=True, autoincrement=True)
    org_id         = Column(String, ForeignKey("organizations.org_id"), nullable=False)
    event_type     = Column(String)  # created, upgraded, downgraded, cancelled
    old_plan       = Column(String, nullable=True)
    new_plan       = Column(String, nullable=True)
    stripe_event_id = Column(String, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class UsageLog(Base):
    """Daily interview count per org — for quota enforcement."""
    __tablename__ = "usage_logs"
    
    id              = Column(Integer, primary_key=True, autoincrement=True)
    org_id          = Column(String, ForeignKey("organizations.org_id"), nullable=False)
    interview_date  = Column(String)  # YYYY-MM-DD
    count           = Column(Integer, default=1)
    created_at      = Column(DateTime, default=datetime.utcnow)


# ── Init ──────────────────────────────────────────────────────────────────

def init_saas_db():
    """Create SaaS tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# ── Organization CRUD ─────────────────────────────────────────────────────

def create_organization(org_name: str, owner_email: str) -> str:
    """
    Create a new organization with trial plan.
    Returns the org_id.
    """
    init_saas_db()
    db = SessionLocal()
    try:
        org_id = str(uuid.uuid4())
        trial_expires = datetime.utcnow() + timedelta(days=14)
        
        org = Organization(
            org_id=org_id,
            org_name=org_name,
            owner_email=owner_email,
            subscription_plan="trial",
            api_key=str(uuid.uuid4()),
            max_interviews_per_month=50,  # trial limit
            trial_started_at=datetime.utcnow(),
            trial_expires_at=trial_expires,
            current_month=datetime.utcnow().strftime("%Y-%m"),
        )
        db.add(org)
        db.commit()
        
        # Log creation
        log = SubscriptionLog(
            org_id=org_id,
            event_type="created",
            new_plan="trial"
        )
        db.add(log)
        db.commit()
        
        return org_id
    finally:
        db.close()


def get_organization(org_id: str):
    """Get organization by org_id."""
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(org_id=org_id).first()
    finally:
        db.close()


def get_organization_by_email(email: str):
    """Get organization by owner email."""
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(owner_email=email).first()
    finally:
        db.close()


def get_organization_by_api_key(api_key: str):
    """Get organization by API key."""
    db = SessionLocal()
    try:
        return db.query(Organization).filter_by(api_key=api_key).first()
    finally:
        db.close()


# ── Subscription Management ───────────────────────────────────────────────

def upgrade_plan(org_id: str, new_plan: str, stripe_subscription_id: str = None):
    """
    Upgrade organization to a new plan.
    Plans: trial (50 interviews/mo), starter (100), pro (500), enterprise (unlimited).
    """
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if not org:
            return False
        
        old_plan = org.subscription_plan
        
        # Set limits per plan
        limits = {
            "trial": 50,
            "starter": 100,
            "pro": 500,
            "enterprise": 9999,
        }
        
        org.subscription_plan = new_plan
        org.max_interviews_per_month = limits.get(new_plan, 50)
        org.stripe_subscription_id = stripe_subscription_id
        org.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Log event
        log = SubscriptionLog(
            org_id=org_id,
            event_type="upgraded" if new_plan != old_plan else "renewed",
            old_plan=old_plan,
            new_plan=new_plan,
            stripe_event_id=stripe_subscription_id
        )
        db.add(log)
        db.commit()
        
        return True
    finally:
        db.close()


def is_trial_expired(org_id: str) -> bool:
    """Check if trial period has ended."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if not org:
            return True
        if org.subscription_plan != "trial":
            return False
        return org.trial_expires_at < datetime.utcnow()
    finally:
        db.close()


# ── Usage Tracking ────────────────────────────────────────────────────────

def check_usage_quota(org_id: str) -> tuple:
    """
    Check if org can conduct another interview.
    Returns (allowed: bool, message: str, used: int, limit: int)
    """
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if not org:
            return False, "Organization not found", 0, 0
        
        if not org.active:
            return False, "Organization account is inactive", 0, 0
        
        # Check trial expiration
        if org.subscription_plan == "trial" and is_trial_expired(org_id):
            return False, "Trial period expired. Please upgrade to continue.", org.used_interviews, org.max_interviews_per_month
        
        # Check monthly quota
        if org.used_interviews >= org.max_interviews_per_month:
            return False, f"Monthly limit reached ({org.used_interviews}/{org.max_interviews_per_month}). Upgrade your plan.", org.used_interviews, org.max_interviews_per_month
        
        return True, "OK", org.used_interviews, org.max_interviews_per_month
    finally:
        db.close()


def increment_interview_count(org_id: str):
    """Call after save_session() — increments monthly counter."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if org:
            org.used_interviews += 1
            org.updated_at = datetime.utcnow()
            db.commit()
            
            # Also log to usage_logs for analytics
            today = datetime.utcnow().strftime("%Y-%m-%d")
            usage = db.query(UsageLog).filter_by(org_id=org_id, interview_date=today).first()
            if usage:
                usage.count += 1
            else:
                usage = UsageLog(org_id=org_id, interview_date=today, count=1)
                db.add(usage)
            db.commit()
    finally:
        db.close()


def reset_monthly_quota(org_id: str):
    """
    Reset used_interviews counter for new month.
    Call this on first interview of new calendar month.
    """
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if org:
            current_month = datetime.utcnow().strftime("%Y-%m")
            if org.current_month != current_month:
                org.used_interviews = 0
                org.current_month = current_month
                db.commit()
    finally:
        db.close()


def get_usage_stats(org_id: str) -> dict:
    """Get usage summary for dashboard."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if not org:
            return {}
        
        # Count interviews this month
        usage_logs = db.query(UsageLog).filter_by(org_id=org_id).all()
        total_interviews = sum(u.count for u in usage_logs)
        
        return {
            "plan": org.subscription_plan,
            "used": org.used_interviews,
            "limit": org.max_interviews_per_month,
            "remaining": max(0, org.max_interviews_per_month - org.used_interviews),
            "trial_expires_at": org.trial_expires_at.isoformat() if org.trial_expires_at else None,
            "is_expired": is_trial_expired(org_id),
        }
    finally:
        db.close()


# ── Stripe Integration ─────────────────────────────────────────────────────

def handle_stripe_webhook(event_type: str, org_id: str, data: dict):
    """
    Handle Stripe webhook events.
    event_type: 'customer.subscription.updated', 'customer.subscription.deleted', etc.
    """
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if not org:
            return False
        
        if event_type == "customer.subscription.updated":
            status = data.get("status")  # active, past_due, canceled
            plan = data.get("plan", "starter")
            
            if status == "active":
                upgrade_plan(org_id, plan, data.get("id"))
            elif status == "canceled":
                org.subscription_plan = "cancelled"
                org.active = 0
                db.commit()
        
        return True
    finally:
        db.close()