"""
saas_auth.py
-----------
Multi-tenant authentication for PsySense SaaS.
Replaces the simple login/register with org creation + email verification.
"""

from .saas_db import (
    init_saas_db, create_organization, get_organization,
    get_organization_by_email, get_organization_by_api_key,
    is_trial_expired, get_usage_stats
)
from database import init_db, verify_login, register_student
import streamlit as st
import re


def validate_email(email: str) -> bool:
    """Basic email validation."""
    return re.match(r"^[^@]+@[^@]+\.[^@]+$", email) is not None


def validate_password(password: str) -> tuple:
    """Validate password strength. Returns (is_valid, message)."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    return True, "OK"


def show_saas_login_signup():
    """
    Main auth UI for SaaS.
    Two flows:
      1. Recruiter signup → create organization → auto-create owner account
      2. Candidate login → simple login (no org creation)
    """
    init_saas_db()
    init_db()
    
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align:center;margin-bottom:32px">
          <div style="width:56px;height:56px;background:var(--navy-mid);border-radius:16px;
               display:inline-flex;align-items:center;justify-content:center;
               font-size:18px;font-weight:800;color:#fff;margin-bottom:14px;
               box-shadow:0 6px 24px rgba(15,15,30,0.28)">PS</div>
          <div style="font-size:22px;font-weight:800;color:var(--text);letter-spacing:-0.5px">PsySense</div>
          <div style="font-size:13px;color:var(--muted);margin-top:5px">AI-powered behavioral interview platform</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="ps-card" style="padding:24px 26px">', unsafe_allow_html=True)
        
        auth_mode = st.radio(
            "I am a",
            ["🏢  Recruiter (login)", "🏢  Recruiter (signup)", "🎤  Candidate (login)"],
            horizontal=True,
            label_visibility="collapsed"
        )

        if auth_mode == "🏢  Recruiter (signup)":
            show_recruiter_signup()
        elif auth_mode == "🎤  Candidate (login)":
            show_candidate_login()
        else:
            show_recruiter_login()

        st.markdown('</div>', unsafe_allow_html=True)
        


def show_candidate_login():
    """Simple candidate login — existing code flow."""
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.form("candidate_login"):
        l_user = st.text_input("Username", placeholder="your_username")
        l_pass = st.text_input("Password", type="password", placeholder="••••••••")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Sign In →", type="primary", use_container_width=True)
    
    if submitted:
        if not l_user or not l_pass:
            st.warning("Please enter both username and password.")
        else:
            user = verify_login(l_user.strip(), l_pass)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_role = user["role"]
                st.session_state.auth_username = user["username"]
                st.session_state.auth_display_name = user["display_name"]
                st.session_state.user_email = user.get("email")
                if user["role"] == "recruiter":
                    from database import SessionLocal, User
                    _db = SessionLocal()
                    try:
                        _u = _db.query(User).filter_by(username=user["username"]).first()
                        if _u and _u.org_id:
                            st.session_state.org_id = _u.org_id
                    finally:
                        _db.close()
                # Load candidate's assigned JD if exists
                if user["role"] == "student":
                    st.session_state.candidate_name = user["display_name"]
                    from database import get_profile_by_username, get_job_posting_by_id
                    profile = get_profile_by_username(user["username"])
                    if profile:
                        st.session_state.jd_id = profile.jd_id
                        posting = get_job_posting_by_id(profile.jd_id)
                        if posting:
                            st.session_state.jd_text = posting.jd_text
                
                st.rerun()
            else:
                st.error("Incorrect username or password.")

    st.markdown("""
    <div style="margin-top:16px;padding:11px 14px;background:var(--bg);
         border-radius:9px;border:1px solid var(--border)">
      <div style="font-size:10px;color:#aaaabc;font-weight:700;
           text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px">Demo candidate</div>
      <div style="font-size:12px;color:var(--muted);font-family:var(--mono)">
        Ask your recruiter for login credentials
      </div>
    </div>
    """, unsafe_allow_html=True)


def show_recruiter_signup():
    """Recruiter signup: create org + create owner account."""
    st.markdown("""
    <div style="padding:12px 14px;background:#eff6ff;border-radius:10px;
         border:1px solid #bfdbfe;margin-bottom:16px;font-size:13px;color:#1e40af">
      ✨ <strong>14-day free trial</strong> — no credit card required. Upgrade anytime.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    
    with st.form("recruiter_signup"):
        org_name = st.text_input(
            "Company/Team Name",
            placeholder="e.g., Acme Corp, TechStartup"
        )
        
        email = st.text_input(
            "Work Email",
            placeholder="you@company.com"
        )
        
        password = st.text_input(
            "Password",
            type="password",
            placeholder="min 8 chars, must include a number"
        )
        
        confirm = st.text_input(
            "Confirm Password",
            type="password",
            placeholder="repeat password"
        )
        
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "Create Account & Start Free Trial →",
            type="primary",
            use_container_width=True
        )
    
    if submitted:
        # Validation
        if not org_name.strip():
            st.error("Please enter your company/team name.")
            return
        
        if not email.strip():
            st.error("Please enter your work email.")
            return
        
        if not validate_email(email):
            st.error("Please enter a valid email address.")
            return
        
        if password != confirm:
            st.error("Passwords do not match.")
            return
        
        valid, msg = validate_password(password)
        if not valid:
            st.error(msg)
            return
        
        # Check if email already registered
        existing_org = get_organization_by_email(email)
        if existing_org:
            st.error("This email is already registered. Please log in or use a different email.")
            return
        
        # Create organization
        try:
            org_id = create_organization(org_name.strip(), email.strip())
            
            # Create owner user account
            # Username = first part of email
            username = email.split('@')[0].lower()
            ok, reg_msg = register_student(
                username=username,
                password=password,
                display_name=org_name.strip(),
                email=email.strip()
            )
            
            if not ok:
                st.error(f"Failed to create account: {reg_msg}")
                return
            
            # Mark this user as recruiter + associate with org
            from database import SessionLocal, User
            db = SessionLocal()
            try:
                user = db.query(User).filter_by(username=username).first()
                if user:
                    user.role = "recruiter"
                    user.org_id = org_id
                    db.commit()
            finally:
                db.close()
            st.session_state.org_id = org_id
            st.success("✨ Account created!")
            st.balloons()
            st.markdown(f"""
            <div style="margin-top:16px;padding:16px 20px;background:#effaf4;
                 border-radius:12px;border:1px solid #b6f0cc">
              <div style="font-size:14px;font-weight:600;color:#166534;margin-bottom:8px">
                Welcome to PsySense, {org_name}! 🎉</div>
              <div style="font-size:13px;color:#1b4d2e;line-height:1.7;margin-bottom:12px">
                <strong>Your 14-day free trial is active.</strong> You can conduct up to <strong>50 interviews</strong> during the trial.
                <br><br>
                Log in with:<br>
                <code style="background:#0d3b1a;color:#22c55e;padding:2px 6px;border-radius:4px;font-size:12px">
                  {username}
                </code>
              </div>
              <div style="font-size:12px;color:#1b4d2e">
                ✓ Next: upgrade to <strong>Starter</strong> ($99/mo, 100 interviews) or <strong>Pro</strong> ($299/mo, 500 interviews)
              </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.info(f"**Redirecting to login in 3 seconds...**")
            import time
            time.sleep(3)
            st.rerun()
            
        except Exception as e:
            st.error(f"Error creating organization: {str(e)}")

def show_recruiter_login():
    """Recruiter login — loads org_id into session."""
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.form("recruiter_login"):
        l_user = st.text_input("Username", placeholder="your_username")
        l_pass = st.text_input("Password", type="password", placeholder="••••••••")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Sign In →", type="primary", use_container_width=True)

    if submitted:
        if not l_user or not l_pass:
            st.warning("Please enter both username and password.")
        else:
            user = verify_login(l_user.strip(), l_pass)
            if user and user["role"] == "recruiter":
                st.session_state.logged_in         = True
                st.session_state.user_role         = "recruiter"
                st.session_state.auth_username     = user["username"]
                st.session_state.auth_display_name = user["display_name"]
                st.session_state.user_email        = user.get("email")

                # Load org_id
                from database import SessionLocal, User
                _db = SessionLocal()
                try:
                    _u = _db.query(User).filter_by(
                        username=user["username"]
                    ).first()
                    if _u and _u.org_id:
                        st.session_state.org_id = _u.org_id
                finally:
                    _db.close()

                st.rerun()
            elif user and user["role"] != "recruiter":
                st.error("This account is not a recruiter account. Use Candidate login.")
            else:
                st.error("Incorrect username or password.")

    st.markdown("""
    <div style="margin-top:16px;padding:11px 14px;background:var(--bg);
         border-radius:9px;border:1px solid var(--border)">
      <div style="font-size:10px;color:#aaaabc;font-weight:700;
           text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px">New here?</div>
      <div style="font-size:12px;color:var(--muted)">
        Switch to <strong>Recruiter (signup)</strong> to create your company account.
      </div>
    </div>
    """, unsafe_allow_html=True)
def show_saas_billing_sidebar(org_id: str):
    """
    Show SaaS billing info for recruiters.
    Call inside an active ``with st.sidebar:`` block (do not nest another sidebar context).
    """
    stats = get_usage_stats(org_id)

    if not stats:
        return

    st.markdown("---")
    st.markdown("""
    <div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;
         letter-spacing:0.8px;margin-bottom:8px">📊 Plan & Usage</div>
    """, unsafe_allow_html=True)

    plan_badge = stats["plan"].upper()
    plan_color = "#10b981" if stats["plan"] == "pro" else "#3b82f6" if stats["plan"] == "starter" else "#f59e0b"

    st.markdown(f"""
    <div style="padding:12px 12px;background:var(--bg);border-radius:10px;
         border:1px solid var(--border);margin-bottom:12px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:12px;font-weight:600;color:var(--text)">Plan</span>
        <span style="background:{plan_color};color:#fff;padding:2px 10px;border-radius:6px;
             font-size:10px;font-weight:700">{plan_badge}</span>
      </div>

      <div style="font-size:12px;color:var(--muted);margin-bottom:8px">
        <strong>{stats['used']}</strong> / <strong>{stats['limit']}</strong> interviews
      </div>

      <div style="background:var(--border);border-radius:6px;height:6px;overflow:hidden">
        <div style="background:#4f46e5;height:100%;width:{int(stats['used']/max(stats['limit'],1)*100)}%"></div>
      </div>

      <div style="font-size:11px;color:var(--muted);margin-top:8px;text-align:right">
        {stats['remaining']} remaining
      </div>
    </div>
    """, unsafe_allow_html=True)

    if stats["plan"] == "trial" and stats["is_expired"]:
        st.error("⚠️ Trial expired — upgrade to continue", icon="⏰")
        if st.button("Upgrade Plan", use_container_width=True, key="saas_upgrade_expired"):
            st.session_state.show_billing_page = True
            st.rerun()
    elif stats["plan"] == "trial":
        if stats["trial_expires_at"]:
            from datetime import datetime
            exp = datetime.fromisoformat(stats["trial_expires_at"])
            days_left = (exp - datetime.utcnow()).days
            st.info(f"Trial ends in {days_left} days", icon="ℹ️")
        if st.button("💳 Upgrade to Paid", use_container_width=True, key="sidebar_upgrade"):
            st.session_state.show_billing_page = True
            st.rerun()
    elif stats["remaining"] < 10:
        st.warning(f"Low on interviews — {stats['remaining']} left", icon="⚠️")