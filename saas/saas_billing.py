"""
saas_billing.py
---------------
Professional billing UI with optional Stripe integration.
When Stripe is not installed, the page still works in local demo mode.
"""

import os
from datetime import datetime

try:
    import stripe  # type: ignore
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None
    STRIPE_AVAILABLE = False

from saas.saas_db import (
    SessionLocal,
    Organization,
    get_organization,
    get_usage_stats,
    init_saas_db,
    upgrade_plan,
    get_subscription_logs,
)

# Initialize Stripe API only when installed
if STRIPE_AVAILABLE:
    stripe.api_key = os.getenv("STRIPE_API_KEY", "")

# Stripe product/price IDs — configure these in Stripe dashboard
PLANS = {
    "starter": {
        "price_id": os.getenv("STRIPE_PRICE_STARTER", "price_1Starter"),
        "name": "Starter",
        "cost": "$99/month",
        "interviews": 100,
    },
    "pro": {
        "price_id": os.getenv("STRIPE_PRICE_PRO", "price_1Pro"),
        "name": "Pro",
        "cost": "$299/month",
        "interviews": 500,
    },
    "enterprise": {
        "price_id": os.getenv("STRIPE_PRICE_ENTERPRISE", "price_1Enterprise"),
        "name": "Enterprise",
        "cost": "Custom",
        "interviews": "Unlimited",
    },
}

APP_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")


def create_checkout_session(org_id: str, plan: str) -> str:
    """
    Create a Stripe checkout session for plan upgrade.
    Returns the checkout URL.
    """
    if not STRIPE_AVAILABLE:
        raise RuntimeError("Stripe SDK not installed. Running billing in demo mode.")

    org = get_organization(org_id)
    if not org:
        raise ValueError("Organization not found")

    if plan not in PLANS:
        raise ValueError(f"Invalid plan: {plan}")

    # If no Stripe customer, create one
    if not org.stripe_customer_id:
        customer = stripe.Customer.create(
            email=org.owner_email,
            name=org.org_name,
            metadata={"org_id": org_id}
        )
        # Persist customer ID so later checkouts can reuse it.
        db = SessionLocal()
        try:
            db_org = db.query(Organization).filter_by(org_id=org_id).first()
            if db_org:
                db_org.stripe_customer_id = customer["id"]
                db_org.updated_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
    else:
        customer = {"id": org.stripe_customer_id}

    # Create checkout session
    success_url = f"{APP_URL}?billing=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{APP_URL}?billing=cancel"

    session = stripe.checkout.Session.create(
        customer=customer["id"],
        payment_method_types=["card"],
        line_items=[{
            "price": PLANS[plan]["price_id"],
            "quantity": 1,
        }],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "org_id": org_id,
            "plan": plan,
        }
    )

    return session.url


def handle_subscription_webhook(event: dict) -> bool:
    """
    Handle Stripe webhook events.
    Main events: customer.subscription.updated, customer.subscription.deleted
    """
    if not STRIPE_AVAILABLE:
        return False

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    org_id = data.get("metadata", {}).get("org_id")

    if not org_id:
        print(f"[Stripe] No org_id in webhook data")
        return False

    if event_type == "customer.subscription.updated":
        status = data.get("status")  # active, past_due, canceled
        plan = data.get("items", {}).get("data", [{}])[0].get("plan", {}).get("metadata", {}).get("plan", "starter")

        if status == "active":
            success = upgrade_plan(org_id, plan, data.get("id"))
            print(f"[Stripe] {org_id} upgraded to {plan}")
            return success
        else:
            print(f"[Stripe] {org_id} subscription status: {status}")
            return False

    elif event_type == "customer.subscription.deleted":
        # Mark org as inactive
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(org_id=org_id).first()
            if org:
                org.active = 0
                org.updated_at = datetime.utcnow()
                db.commit()
                print(f"[Stripe] subscription cancelled for {org_id}")
                return True
        finally:
            db.close()

    return False


# ── Colors & Styles ───────────────────────────────────────────────────────

_BILLING_CSS = """
<style>
.billing-header {
    text-align: center;
    margin-bottom: 32px;
}
.billing-header h2 {
    font-size: 26px;
    font-weight: 800;
    color: #111827;
    margin: 0 0 6px;
}
.billing-header p {
    font-size: 14px;
    color: #6b7280;
    margin: 0;
}
.plan-card {
    background: #fff;
    border: 2px solid #e5e7eb;
    border-radius: 16px;
    padding: 28px 24px;
    text-align: center;
    transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
    height: 100%;
}
.plan-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.08);
}
.plan-card.popular {
    border-color: #4f46e5;
    background: linear-gradient(180deg, #f5f3ff 0%, #fff 40%);
    box-shadow: 0 8px 32px rgba(79,70,229,0.12);
}
.plan-badge {
    display: inline-block;
    background: #4f46e5;
    color: #fff;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
}
.plan-name {
    font-size: 20px;
    font-weight: 700;
    color: #111827;
    margin: 0 0 8px;
}
.plan-price {
    font-size: 36px;
    font-weight: 800;
    margin: 0 0 4px;
}
.plan-price span {
    font-size: 15px;
    font-weight: 500;
    color: #6b7280;
}
.plan-interviews {
    font-size: 13px;
    color: #6b7280;
    margin-bottom: 20px;
}
.plan-features {
    list-style: none;
    padding: 0;
    margin: 0 0 20px;
    text-align: left;
}
.plan-features li {
    font-size: 13px;
    color: #374151;
    padding: 6px 0;
    border-bottom: 1px solid #f3f4f6;
}
.plan-features li:last-child {
    border-bottom: none;
}
.plan-features li::before {
    content: "\\2713";
    color: #10b981;
    font-weight: 700;
    margin-right: 10px;
}
.usage-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 20px 24px;
}
.usage-progress-bg {
    background: #e5e7eb;
    border-radius: 8px;
    height: 10px;
    overflow: hidden;
    margin: 10px 0;
}
.usage-progress-fill {
    height: 100%;
    border-radius: 8px;
    transition: width 0.6s ease;
}
.history-row {
    display: flex;
    align-items: center;
    padding: 10px 14px;
    border-bottom: 1px solid #f3f4f6;
    gap: 16px;
}
.history-row:last-child { border-bottom: none; }
.history-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
</style>
"""


def show_billing_page(org_id: str):
    """
    Streamlit billing/plans page for recruiter dashboard.
    Shows current plan, usage, and upgrade options.
    """
    import streamlit as st

    init_saas_db()
    org = get_organization(org_id)
    stats = get_usage_stats(org_id)

    if not org:
        st.error("Organization not found")
        return

    st.markdown(_BILLING_CSS, unsafe_allow_html=True)

    # ── Header ──
    st.markdown("""
    <div class="billing-header">
        <h2>Billing & Plan</h2>
        <p>Manage your subscription, usage, and payment details</p>
    </div>
    """, unsafe_allow_html=True)

    if not STRIPE_AVAILABLE:
        st.info("Demo billing mode — Stripe not installed. Local billing tables are active.")

    # ── Current Plan Summary ──
    plan_label = (org.subscription_plan or "trial").upper()
    plan_colors = {
        "TRIAL": ("#f59e0b", "#fef3c7"),
        "STARTER": ("#3b82f6", "#dbeafe"),
        "PRO": ("#4f46e5", "#e0e7ff"),
        "ENTERPRISE": ("#059669", "#d1fae5"),
    }
    pc, pc_bg = plan_colors.get(plan_label, ("#6b7280", "#f3f4f6"))

    remaining_days = None
    status_text = "Active"
    if org.subscription_plan == "trial" and org.trial_expires_at:
        remaining_days = (org.trial_expires_at - datetime.utcnow()).days
        status_text = f"{remaining_days} days left" if remaining_days > 0 else "Expired"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="usage-card" style="text-align:center">
            <div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;
                 letter-spacing:0.8px;margin-bottom:6px">Current Plan</div>
            <div style="display:inline-block;background:{pc_bg};color:{pc};
                 padding:6px 18px;border-radius:8px;font-size:16px;font-weight:800">{plan_label}</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="usage-card" style="text-align:center">
            <div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;
                 letter-spacing:0.8px;margin-bottom:6px">Interviews Used</div>
            <div style="font-size:24px;font-weight:800;color:#111827">{stats['used']}<span style="font-size:14px;color:#9ca3af">/{stats['limit']}</span></div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        pct = int(stats['used'] / max(stats['limit'], 1) * 100)
        fill_color = "#10b981" if pct < 70 else ("#f59e0b" if pct < 90 else "#ef4444")
        st.markdown(f"""
        <div class="usage-card" style="text-align:center">
            <div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;
                 letter-spacing:0.8px;margin-bottom:6px">Usage</div>
            <div class="usage-progress-bg">
                <div class="usage-progress-fill" style="width:{pct}%;background:{fill_color}"></div>
            </div>
            <div style="font-size:12px;color:#6b7280;margin-top:4px">{stats['remaining']} remaining</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="usage-card" style="text-align:center">
            <div style="font-size:11px;font-weight:700;color:#9ca3af;text-transform:uppercase;
                 letter-spacing:0.8px;margin-bottom:6px">Status</div>
            <div style="font-size:18px;font-weight:700;color:{pc}">{status_text}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ── Pricing Cards ──
    st.markdown("""
    <div style="text-align:center;margin-bottom:20px">
        <div style="font-size:18px;font-weight:700;color:#111827">Choose Your Plan</div>
        <div style="font-size:13px;color:#6b7280;margin-top:4px">Scale your hiring with the right plan</div>
    </div>
    """, unsafe_allow_html=True)

    plan_cols = st.columns(3, gap="large")

    # Starter
    with plan_cols[0]:
        is_current = org.subscription_plan == "starter"
        st.markdown(f"""
        <div class="plan-card">
            <div class="plan-name">Starter</div>
            <div class="plan-price" style="color:#111827">$99<span>/mo</span></div>
            <div class="plan-interviews">100 interviews per month</div>
            <ul class="plan-features">
                <li>Multi-user access</li>
                <li>Basic analytics dashboard</li>
                <li>PDF candidate reports</li>
                <li>Email support</li>
            </ul>
            {'<div style="font-size:13px;color:#10b981;font-weight:700;padding:8px 0">Current Plan</div>' if is_current else ''}
        </div>
        """, unsafe_allow_html=True)
        if not is_current:
            if st.button("Upgrade to Starter", use_container_width=True, key="plan_starter"):
                try:
                    url = create_checkout_session(org_id, "starter")
                    st.markdown(f"[Complete Payment on Stripe]({url})")
                except RuntimeError:
                    st.info("Payment processing coming soon. Contact sales@psysense.app")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Pro
    with plan_cols[1]:
        is_current = org.subscription_plan == "pro"
        st.markdown(f"""
        <div class="plan-card popular">
            <div class="plan-badge">MOST POPULAR</div>
            <div class="plan-name">Pro</div>
            <div class="plan-price" style="color:#4f46e5">$299<span>/mo</span></div>
            <div class="plan-interviews">500 interviews per month</div>
            <ul class="plan-features">
                <li>Everything in Starter</li>
                <li>API access & webhooks</li>
                <li>Advanced analytics & trends</li>
                <li>Priority support</li>
                <li>Custom branding</li>
            </ul>
            {'<div style="font-size:13px;color:#10b981;font-weight:700;padding:8px 0">Current Plan</div>' if is_current else ''}
        </div>
        """, unsafe_allow_html=True)
        if not is_current:
            if st.button("Upgrade to Pro", type="primary", use_container_width=True, key="plan_pro"):
                try:
                    url = create_checkout_session(org_id, "pro")
                    st.markdown(f"[Complete Payment on Stripe]({url})")
                except RuntimeError:
                    st.info("Payment processing coming soon. Contact sales@psysense.app")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

    # Enterprise
    with plan_cols[2]:
        is_current = org.subscription_plan == "enterprise"
        st.markdown(f"""
        <div class="plan-card">
            <div class="plan-name">Enterprise</div>
            <div class="plan-price" style="color:#111827">Custom</div>
            <div class="plan-interviews">Unlimited interviews</div>
            <ul class="plan-features">
                <li>Everything in Pro</li>
                <li>Dedicated account manager</li>
                <li>Custom AI model tuning</li>
                <li>SSO & SAML integration</li>
                <li>On-premise deployment</li>
                <li>SLA guarantee</li>
            </ul>
            {'<div style="font-size:13px;color:#10b981;font-weight:700;padding:8px 0">Current Plan</div>' if is_current else ''}
        </div>
        """, unsafe_allow_html=True)
        if not is_current:
            if st.button("Contact Sales", use_container_width=True, key="plan_enterprise"):
                st.markdown(
                    "**[Schedule a call](mailto:sales@psysense.app?subject=Enterprise%20Plan%20Inquiry)**"
                    " or email **sales@psysense.app**"
                )

    st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)

    # ── Usage Details ──
    st.markdown("""
    <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:14px">
        Usage Details
    </div>
    """, unsafe_allow_html=True)

    u1, u2 = st.columns(2)
    with u1:
        st.markdown(f"""
        <div class="usage-card">
            <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:8px">
                Monthly Usage
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;color:#6b7280;margin-bottom:4px">
                <span>Interviews conducted</span>
                <strong style="color:#111827">{stats['used']}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;color:#6b7280;margin-bottom:4px">
                <span>Monthly limit</span>
                <strong style="color:#111827">{stats['limit']}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;color:#6b7280">
                <span>Remaining quota</span>
                <strong style="color:#10b981">{stats['remaining']}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with u2:
        st.markdown(f"""
        <div class="usage-card">
            <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:8px">
                Billing Info
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;color:#6b7280;margin-bottom:4px">
                <span>Organization</span>
                <strong style="color:#111827">{org.org_name}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;color:#6b7280;margin-bottom:4px">
                <span>Billing period</span>
                <strong style="color:#111827">{org.current_month or 'N/A'}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:13px;color:#6b7280">
                <span>Last updated</span>
                <strong style="color:#111827">{org.updated_at.strftime('%d %b %Y, %H:%M') if org.updated_at else 'N/A'}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    # ── Subscription History ──
    st.markdown("""
    <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:14px">
        Subscription History
    </div>
    """, unsafe_allow_html=True)

    logs = get_subscription_logs(org_id, limit=25)

    EVENT_CONFIG = {
        "created": ("#10b981", "Account created"),
        "upgraded": ("#4f46e5", "Plan upgraded"),
        "renewed": ("#3b82f6", "Plan renewed"),
        "downgraded": ("#f59e0b", "Plan downgraded"),
        "cancelled": ("#ef4444", "Subscription cancelled"),
    }

    if logs:
        for log in logs:
            cfg = EVENT_CONFIG.get(log.event_type, ("#9ca3af", log.event_type or "Event"))
            dot_color, label = cfg
            dt = log.created_at.strftime("%d %b %Y, %H:%M") if log.created_at else "-"
            plan_info = ""
            if log.old_plan and log.new_plan:
                plan_info = f"{log.old_plan} → {log.new_plan}"
            elif log.new_plan:
                plan_info = log.new_plan

            st.markdown(f"""
            <div class="history-row">
                <div class="history-dot" style="background:{dot_color}"></div>
                <div style="flex:1">
                    <div style="font-size:13px;font-weight:600;color:#111827">{label}</div>
                    <div style="font-size:12px;color:#9ca3af">{dt}</div>
                </div>
                <div style="font-size:13px;color:#6b7280">{plan_info}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="usage-card" style="text-align:center;padding:24px;color:#9ca3af">
            <div style="font-size:13px">No subscription events yet</div>
            <div style="font-size:12px;margin-top:4px">Current plan: <strong>{org.subscription_plan or 'trial'}</strong></div>
        </div>
        """, unsafe_allow_html=True)