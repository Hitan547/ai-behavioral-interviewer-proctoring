"""
saas_billing.py
---------------
Professional billing UI with Razorpay integration.
When Razorpay is not installed, the page still works in local demo mode.

Razorpay setup:
  1. Create account at https://razorpay.com
  2. Get key_id and key_secret from Dashboard → Settings → API Keys
  3. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env
  4. Create subscription plans in Dashboard → Products → Subscriptions
"""

import os
from datetime import datetime

try:
    import razorpay  # type: ignore
    RAZORPAY_AVAILABLE = True
except ImportError:
    razorpay = None
    RAZORPAY_AVAILABLE = False

from saas.saas_db import (
    SessionLocal,
    Organization,
    get_organization,
    get_usage_stats,
    init_saas_db,
    upgrade_plan,
    get_subscription_logs,
)

# Initialize Razorpay client only when installed
_razorpay_client = None
if RAZORPAY_AVAILABLE:
    _key_id = os.getenv("RAZORPAY_KEY_ID", "")
    _key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if _key_id and _key_secret:
        _razorpay_client = razorpay.Client(auth=(_key_id, _key_secret))


# Plan configuration
PLANS = {
    "starter": {
        "name": "Starter",
        "cost": "₹8,250/month",
        "cost_usd": "$99/month",
        "amount_paise": 825000,  # ₹8,250 in paise
        "interviews": 100,
        "razorpay_plan_id": os.getenv("RAZORPAY_PLAN_STARTER", ""),
    },
    "pro": {
        "name": "Pro",
        "cost": "₹24,900/month",
        "cost_usd": "$299/month",
        "amount_paise": 2490000,  # ₹24,900 in paise
        "interviews": 500,
        "razorpay_plan_id": os.getenv("RAZORPAY_PLAN_PRO", ""),
    },
    "enterprise": {
        "name": "Enterprise",
        "cost": "Custom",
        "cost_usd": "Custom",
        "amount_paise": 0,
        "interviews": "Unlimited",
        "razorpay_plan_id": os.getenv("RAZORPAY_PLAN_ENTERPRISE", ""),
    },
}

APP_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")


def create_razorpay_order(org_id: str, plan: str) -> dict:
    """
    Create a Razorpay order for plan upgrade.
    Returns order details for frontend checkout.
    """
    if not _razorpay_client:
        raise RuntimeError("Razorpay not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.")

    org = get_organization(org_id)
    if not org:
        raise ValueError("Organization not found")

    if plan not in PLANS or plan == "enterprise":
        raise ValueError(f"Invalid plan: {plan}")

    plan_info = PLANS[plan]

    order_data = {
        "amount": plan_info["amount_paise"],
        "currency": "INR",
        "receipt": f"psysense_{org_id}_{plan}",
        "notes": {
            "org_id": org_id,
            "plan": plan,
            "org_name": org.org_name,
        },
    }

    order = _razorpay_client.order.create(data=order_data)
    return {
        "order_id": order["id"],
        "amount": plan_info["amount_paise"],
        "currency": "INR",
        "key_id": os.getenv("RAZORPAY_KEY_ID", ""),
        "org_name": org.org_name,
        "email": org.owner_email,
        "plan": plan,
    }


def verify_razorpay_payment(payment_id: str, order_id: str, signature: str) -> bool:
    """Verify payment signature after successful checkout."""
    if not _razorpay_client:
        return False

    try:
        _razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
        return True
    except Exception as e:
        print(f"[razorpay] Payment verification failed: {e}")
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
.razorpay-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #1a1a2e;
    color: #fff;
    padding: 4px 12px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    margin-top: 8px;
}
</style>
"""


def show_billing_page(org_id: str):
    """
    Streamlit billing/plans page for recruiter dashboard.
    Shows current plan, usage, and upgrade options via Razorpay.
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

    if not RAZORPAY_AVAILABLE or not _razorpay_client:
        st.info("💳 **Billing is in demo mode.** Configure Razorpay credentials to enable payments. "
                "Set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in your `.env` file.")

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
        <div style="font-size:13px;color:#6b7280;margin-top:4px">Scale your hiring with the right plan — pay via UPI, cards, or net banking</div>
    </div>
    """, unsafe_allow_html=True)

    plan_cols = st.columns(3, gap="large")

    # Starter
    with plan_cols[0]:
        is_current = org.subscription_plan == "starter"
        st.markdown(f"""
        <div class="plan-card">
            <div class="plan-name">Starter</div>
            <div class="plan-price" style="color:#111827">₹8,250<span>/mo</span></div>
            <div class="plan-interviews">100 interviews per month</div>
            <ul class="plan-features">
                <li>Multi-user access</li>
                <li>Basic analytics dashboard</li>
                <li>PDF candidate reports</li>
                <li>Email support</li>
                <li>Enterprise proctoring</li>
            </ul>
            {'<div style="font-size:13px;color:#10b981;font-weight:700;padding:8px 0">Current Plan</div>' if is_current else ''}
        </div>
        """, unsafe_allow_html=True)
        if not is_current:
            if st.button("Upgrade to Starter", use_container_width=True, key="plan_starter"):
                _handle_upgrade(org_id, "starter", st)

    # Pro
    with plan_cols[1]:
        is_current = org.subscription_plan == "pro"
        st.markdown(f"""
        <div class="plan-card popular">
            <div class="plan-badge">MOST POPULAR</div>
            <div class="plan-name">Pro</div>
            <div class="plan-price" style="color:#4f46e5">₹24,900<span>/mo</span></div>
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
                _handle_upgrade(org_id, "pro", st)

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
                <span>Payment gateway</span>
                <strong style="color:#111827">{'Razorpay' if _razorpay_client else 'Demo Mode'}</strong>
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


def _handle_upgrade(org_id: str, plan: str, st):
    """Handle upgrade button click."""
    if _razorpay_client:
        try:
            order = create_razorpay_order(org_id, plan)
            key_id = order["key_id"]

            # Inject Razorpay checkout JavaScript
            st.markdown(f"""
            <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
            <script>
            var options = {{
                "key": "{key_id}",
                "amount": "{order['amount']}",
                "currency": "INR",
                "name": "PsySense AI",
                "description": "{PLANS[plan]['name']} Plan — {PLANS[plan]['interviews']} interviews/month",
                "order_id": "{order['order_id']}",
                "prefill": {{
                    "email": "{order['email']}",
                    "contact": ""
                }},
                "theme": {{
                    "color": "#4f46e5"
                }},
                "handler": function (response) {{
                    // Redirect with payment details for verification
                    window.location.href = window.location.pathname +
                        "?payment_id=" + response.razorpay_payment_id +
                        "&order_id=" + response.razorpay_order_id +
                        "&signature=" + response.razorpay_signature +
                        "&plan={plan}";
                }}
            }};
            var rzp = new Razorpay(options);
            rzp.open();
            </script>
            """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Payment error: {str(e)}")
    else:
        # Demo mode — upgrade immediately for testing
        success = upgrade_plan(org_id, plan)
        if success:
            st.success(f"✅ Upgraded to **{PLANS[plan]['name']}** plan! (Demo mode — no payment charged)")
            import time
            time.sleep(1)
            st.rerun()
        else:
            st.error("Upgrade failed. Please try again.")