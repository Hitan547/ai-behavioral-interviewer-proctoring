"""
password_reset.py
-----------------
Token-based password reset for PsySense SaaS.

Flow:
  1. User enters email on "Forgot Password?" form
  2. System generates HMAC-signed token, stores in DB
  3. Reset link sent via n8n webhook email
  4. User clicks link → enters new password → token consumed

Security:
  - Tokens expire after 1 hour
  - One-time use (marked as used after successful reset)
  - HMAC-SHA256 signed (not guessable)
"""

import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta

from database import SessionLocal, User, Base, engine
from sqlalchemy import Column, Integer, String, DateTime, Boolean

# ── Token duration ────────────────────────────────────────────────────────

TOKEN_EXPIRY_HOURS = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRY_HOURS", "1"))
_SECRET = os.getenv("PASSWORD_RESET_SECRET", "psysense-reset-secret-change-in-production")


# ── Model ─────────────────────────────────────────────────────────────────

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    token      = Column(String, unique=True, nullable=False, index=True)
    username   = Column(String, nullable=False)
    email      = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used       = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def _init_reset_table():
    """Create the password_reset_tokens table if it doesn't exist."""
    Base.metadata.create_all(bind=engine, tables=[PasswordResetToken.__table__])


# ── Token generation ──────────────────────────────────────────────────────

def generate_reset_token(email: str) -> dict:
    """
    Generate a password reset token for the given email.

    Returns:
        {"success": True, "token": "...", "username": "...", "expires_at": datetime}
        or {"success": False, "error": "..."}
    """
    _init_reset_table()

    db = SessionLocal()
    try:
        # Find user by email (case-insensitive)
        from sqlalchemy import func
        user = db.query(User).filter(
            func.lower(User.email) == email.strip().lower()
        ).first()

        if not user:
            # Don't reveal whether the email exists (security best practice)
            return {"success": False, "error": "If this email is registered, a reset link has been sent."}

        # Invalidate any existing unused tokens for this user
        db.query(PasswordResetToken).filter_by(
            username=user.username, used=False
        ).update({"used": True})
        db.commit()

        # Generate cryptographically secure token
        raw_token = secrets.token_urlsafe(32)
        signed = hmac.new(
            _SECRET.encode(),
            raw_token.encode(),
            hashlib.sha256
        ).hexdigest()

        token_value = f"{raw_token}.{signed[:16]}"
        expires = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)

        reset_token = PasswordResetToken(
            token=token_value,
            username=user.username,
            email=email.strip().lower(),
            expires_at=expires,
        )
        db.add(reset_token)
        db.commit()

        return {
            "success": True,
            "token": token_value,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name or user.username,
            "expires_at": expires,
        }

    except Exception as e:
        print(f"[password_reset] Error generating token: {e}")
        return {"success": False, "error": "Internal error. Please try again."}
    finally:
        db.close()


# ── Token verification ───────────────────────────────────────────────────

def verify_reset_token(token: str) -> dict:
    """
    Verify a password reset token.

    Returns:
        {"valid": True, "username": "...", "email": "..."}
        or {"valid": False, "error": "..."}
    """
    _init_reset_table()

    db = SessionLocal()
    try:
        record = db.query(PasswordResetToken).filter_by(token=token).first()

        if not record:
            return {"valid": False, "error": "Invalid or expired reset link."}

        if record.used:
            return {"valid": False, "error": "This reset link has already been used."}

        if record.expires_at < datetime.utcnow():
            return {"valid": False, "error": "This reset link has expired. Please request a new one."}

        return {
            "valid": True,
            "username": record.username,
            "email": record.email,
        }

    finally:
        db.close()


# ── Execute reset ─────────────────────────────────────────────────────────

def execute_password_reset(token: str, new_password: str) -> dict:
    """
    Reset the password for the user associated with the token.

    Returns:
        {"success": True, "username": "..."}
        or {"success": False, "error": "..."}
    """
    if len(new_password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters."}

    _init_reset_table()

    db = SessionLocal()
    try:
        record = db.query(PasswordResetToken).filter_by(token=token).first()

        if not record or record.used or record.expires_at < datetime.utcnow():
            return {"success": False, "error": "Invalid or expired reset link."}

        # Update the user's password
        import bcrypt
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

        user = db.query(User).filter_by(username=record.username).first()
        if not user:
            return {"success": False, "error": "User account not found."}

        user.password_hash = hashed
        record.used = True
        db.commit()

        return {"success": True, "username": record.username}

    except Exception as e:
        print(f"[password_reset] Error executing reset: {e}")
        return {"success": False, "error": "Internal error. Please try again."}
    finally:
        db.close()


# ── Send reset email via n8n ──────────────────────────────────────────────

def send_reset_email_via_n8n(email: str, reset_url: str, display_name: str = "User") -> bool:
    """
    Send password reset email via n8n webhook.
    Returns True if the webhook responded successfully.
    """
    import requests

    webhook_url = os.getenv("N8N_INVITE_WEBHOOK", "")
    if not webhook_url:
        print("[password_reset] N8N_INVITE_WEBHOOK not configured — cannot send email")
        return False

    try:
        payload = {
            "type": "password_reset",
            "email": email,
            "name": display_name,
            "reset_url": reset_url,
            "subject": "PsySense — Password Reset Request",
            "expires_in": f"{TOKEN_EXPIRY_HOURS} hour(s)",
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code in (200, 201, 202)
    except Exception as e:
        print(f"[password_reset] Failed to send email: {e}")
        return False
