"""
saas_billing.py
---------------
Simple Stripe integration for SaaS subscriptions.
Minimal setup: checkout links + webhook handlers.
"""

import stripe
import os
from saas_db import get_organization, upgrade_plan, handle_stripe_webhook
from datetime import datetime

# Initialize Stripe API
stripe.api_key = os.getenv("STRIPE_API_KEY", "sk_test_your_key_here")

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


def create_checkout_session(org_id: str, plan: str) -> str:
    """
    Create a Stripe checkout session for plan upgrade.
    Returns the checkout URL.
    """
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
        # Update org with customer ID (you'd do this in a transaction in production)
        db_org = get_organization(org_id)
        # Note: In production, use SQLAlchemy session to update
    else:
        customer = {"id": org.stripe_customer_id}
    
    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=customer["id"],
        payment_method_types=["card"],
        line_items=[{
            "price": PLANS[plan]["price_id"],
            "quantity": 1,
        }],
        mode="subscription",
        success_url="https://yourapp.com/billing/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://yourapp.com/billing/cancel",
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
    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    org_id = data.get("metadata", {}).get("org_id")
    
    if not org_id:
        print(f"[Stripe] ⚠️ No org_id in webhook data")
        return False
    
    if event_type == "customer.subscription.updated":
        status = data.get("status")  # active, past_due, canceled
        plan = data.get("items", {}).get("data", [{}])[0].get("plan", {}).get("metadata", {}).get("plan", "starter")
        
        if status == "active":
            success = upgrade_plan(org_id, plan, data.get("id"))
            print(f"[Stripe] ✅ {org_id} upgraded to {plan}")
            return success
        else:
            print(f"[Stripe] ⚠️ {org_id} subscription status: {status}")
            return False
    
    elif event_type == "customer.subscription.deleted":
        # Mark org as inactive
        org = get_organization(org_id)
        if org:
            from saas_db import SessionLocal
            db = SessionLocal()
            try:
                db.query(get_organization.__module__.Organization).filter_by(
                    org_id=org_id
                ).update({"active": 0})
                db.commit()
                print(f"[Stripe] ❌ {org_id} subscription cancelled")
            finally:
                db.close()
            return True
    
    return False


def show_billing_page(org_id: str):
    """
    Streamlit billing/plans page for recruiter dashboard.
    Shows current plan, usage, and upgrade options.
    """
    import streamlit as st
    from saas_db import get_usage_stats
    
    org = get_organization(org_id)
    stats = get_usage_stats(org_id)
    
    if not org:
        st.error("Organization not found")
        return
    
    st.title("💳 Billing & Plan")
    
    # Current plan
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Plan", org.subscription_plan.upper())
    with col2:
        st.metric("Interviews Used", f"{stats['used']}/{stats['limit']}")
    with col3:
        remaining_days = None
        if org.trial_expires_at:
            remaining_days = (org.trial_expires_at - datetime.utcnow()).days
        st.metric("Status", f"{remaining_days} days left" if remaining_days else "Active")
    
    st.markdown("---")
    
    # Pricing cards
    st.subheader("Available Plans")
    
    plan_cols = st.columns(3, gap="large")
    
    # Starter
    with plan_cols[0]:
        st.markdown("""
        <div style="padding:20px;border:2px solid #e4e4ec;border-radius:12px;text-align:center">
          <h3 style="margin:0 0 8px;font-size:18px;font-weight:700">Starter</h3>
          <div style="font-size:28px;font-weight:800;color:#0f0f1e;margin-bottom:10px">$99<span style="font-size:14px">/mo</span></div>
          <div style="font-size:13px;color:#666;margin-bottom:16px">100 interviews/month</div>
          <ul style="font-size:13px;color:#555;text-align:left;list-style:none;padding:0">
            <li>✓ Multi-user access</li>
            <li>✓ Basic analytics</li>
            <li>✓ Email support</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Choose Starter", use_container_width=True, key="plan_starter"):
            st.info("💳 Payment processing coming soon — contact sales@psysense.app")
            try:
                url = create_checkout_session(org_id, "starter")
                st.write(f"[Go to Stripe Checkout]({url})")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Pro
    with plan_cols[1]:
        st.markdown("""
        <div style="padding:20px;border:3px solid #4f46e5;border-radius:12px;text-align:center;background:#f0f4ff">
          <div style="display:inline-block;background:#4f46e5;color:#fff;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;margin-bottom:8px">POPULAR</div>
          <h3 style="margin:8px 0;font-size:18px;font-weight:700">Pro</h3>
          <div style="font-size:28px;font-weight:800;color:#4f46e5;margin-bottom:10px">$299<span style="font-size:14px">/mo</span></div>
          <div style="font-size:13px;color:#666;margin-bottom:16px">500 interviews/month</div>
          <ul style="font-size:13px;color:#555;text-align:left;list-style:none;padding:0">
            <li>✓ Everything in Starter</li>
            <li>✓ API access</li>
            <li>✓ Advanced analytics</li>
            <li>✓ Priority support</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Choose Pro", use_container_width=True, key="plan_pro"):
            try:
                url = create_checkout_session(org_id, "pro")
                st.write(f"[Go to Stripe Checkout]({url})")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    # Enterprise
    with plan_cols[2]:
        st.markdown("""
        <div style="padding:20px;border:2px solid #e4e4ec;border-radius:12px;text-align:center">
          <h3 style="margin:0 0 8px;font-size:18px;font-weight:700">Enterprise</h3>
          <div style="font-size:28px;font-weight:800;color:#0f0f1e;margin-bottom:10px">Custom</div>
          <div style="font-size:13px;color:#666;margin-bottom:16px">Unlimited interviews</div>
          <ul style="font-size:13px;color:#555;text-align:left;list-style:none;padding:0">
            <li>✓ Everything in Pro</li>
            <li>✓ Dedicated support</li>
            <li>✓ Custom integrations</li>
            <li>✓ On-premise option</li>
          </ul>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Contact Sales", use_container_width=True, key="plan_enterprise"):
            st.info("📧 Email sales@psysense.app for enterprise pricing")
    
    st.markdown("---")
    st.subheader("Usage Details")
    
    usage_col1, usage_col2 = st.columns(2)
    with usage_col1:
        st.write(f"**Interviews conducted:** {stats['used']} / {stats['limit']}")
        st.write(f"**Remaining quota:** {stats['remaining']}")
    with usage_col2:
        st.write(f"**Billing period:** {org.current_month}")
        st.write(f"**Last updated:** {org.updated_at.strftime('%Y-%m-%d %H:%M')}")