"""
razorpay_webhooks.py
--------------------
FastAPI app to receive Razorpay payment webhooks.

Run with:
    uvicorn razorpay_webhooks:app --port 8005

Razorpay sends events to this endpoint when:
  - payment.captured  → User paid for a plan
  - subscription.activated → Subscription started
  - subscription.cancelled → Subscription cancelled
  - payment.failed → Payment failed

Setup in Razorpay Dashboard:
  1. Go to Settings → Webhooks
  2. Add URL: https://your-domain.com/razorpay/webhook
  3. Select events: payment.captured, subscription.*
  4. Copy the webhook secret → set as RAZORPAY_WEBHOOK_SECRET env var
"""

import os
import json
import hmac
import hashlib
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException

app = FastAPI(title="PsySense Razorpay Webhooks", version="1.0")

WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature using HMAC-SHA256."""
    if not WEBHOOK_SECRET:
        print("[razorpay] WARNING: RAZORPAY_WEBHOOK_SECRET not set — skipping verification")
        return True  # Allow in dev mode

    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@app.get("/health")
def health():
    return {"status": "ok", "service": "razorpay_webhooks"}


@app.post("/razorpay/webhook")
async def handle_webhook(request: Request):
    """
    Receive and process Razorpay webhook events.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook authenticity
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", "")
    entity = payload.get("payload", {})

    print(f"[razorpay] Received event: {event}")

    if event == "payment.captured":
        await _handle_payment_captured(entity)
    elif event == "subscription.activated":
        await _handle_subscription_activated(entity)
    elif event == "subscription.cancelled":
        await _handle_subscription_cancelled(entity)
    elif event == "payment.failed":
        await _handle_payment_failed(entity)
    else:
        print(f"[razorpay] Unhandled event type: {event}")

    return {"status": "ok"}


async def _handle_payment_captured(entity: dict):
    """
    Process successful payment.
    Extract org_id from payment notes and upgrade the plan.
    """
    payment = entity.get("payment", {}).get("entity", {})
    notes = payment.get("notes", {})
    org_id = notes.get("org_id")
    plan = notes.get("plan", "starter")

    if not org_id:
        print(f"[razorpay] payment.captured but no org_id in notes")
        return

    try:
        from saas.saas_db import upgrade_plan
        success = upgrade_plan(org_id, plan, payment.get("id"))
        print(f"[razorpay] Upgraded {org_id} to {plan}: {'OK' if success else 'FAILED'}")
    except Exception as e:
        print(f"[razorpay] Error upgrading plan: {e}")


async def _handle_subscription_activated(entity: dict):
    """Process subscription activation."""
    subscription = entity.get("subscription", {}).get("entity", {})
    notes = subscription.get("notes", {})
    org_id = notes.get("org_id")
    plan = notes.get("plan", "starter")

    if not org_id:
        return

    try:
        from saas.saas_db import upgrade_plan
        upgrade_plan(org_id, plan, subscription.get("id"))
        print(f"[razorpay] Subscription activated for {org_id}: {plan}")
    except Exception as e:
        print(f"[razorpay] Error activating subscription: {e}")


async def _handle_subscription_cancelled(entity: dict):
    """Process subscription cancellation."""
    subscription = entity.get("subscription", {}).get("entity", {})
    notes = subscription.get("notes", {})
    org_id = notes.get("org_id")

    if not org_id:
        return

    try:
        from saas.saas_db import SessionLocal
        from saas.saas_db import Organization
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(org_id=org_id).first()
            if org:
                org.active = 0
                org.updated_at = datetime.utcnow()
                db.commit()
                print(f"[razorpay] Subscription cancelled for {org_id}")
        finally:
            db.close()
    except Exception as e:
        print(f"[razorpay] Error cancelling subscription: {e}")


async def _handle_payment_failed(entity: dict):
    """Log payment failure — can trigger email notification later."""
    payment = entity.get("payment", {}).get("entity", {})
    notes = payment.get("notes", {})
    org_id = notes.get("org_id")
    error = payment.get("error_description", "Unknown error")

    print(f"[razorpay] Payment FAILED for org {org_id}: {error}")
    # Future: send notification email via n8n
