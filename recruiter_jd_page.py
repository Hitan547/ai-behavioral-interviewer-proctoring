"""
recruiter_jd_page.py
--------------------
Recruiter page for PsySense V2 new flow:
  1. Upload JD + resume PDFs
  2. AI scores and ranks each resume vs JD
  3. Recruiter reviews shortlist, sets threshold + deadline
  4. Recruiter sends invites → accounts auto-created → n8n emails candidates

Import and call show_jd_page() from your main recruiter dashboard.
"""

import io
import os
import json
import time
import re
from pathlib import Path
import requests
import streamlit as st
from datetime import datetime, date
from dotenv import load_dotenv

import PyPDF2

from database import (
    save_job_posting,
    save_candidate_profile,
    create_candidate_account,
    verify_login,
    mark_invite_sent,
    get_all_job_postings,
    get_job_posting_by_id,
    get_candidates_by_jd,
    get_jd_stats,
    check_expired_invites,
    close_job_posting,
)
from matching_service.matcher import score_all_resumes

load_dotenv()

# n8n webhook URL for candidate invite emails
# Set this in your .env as N8N_INVITE_WEBHOOK
N8N_INVITE_WEBHOOK = os.getenv("N8N_INVITE_WEBHOOK", "http://localhost:5678/webhook/candidate-invite")
N8N_INVITE_WORKFLOW_NAME = os.getenv("N8N_INVITE_WORKFLOW_NAME", "My workflow 2")

# Your app's login URL — change to your Cloudflare tunnel URL in production
APP_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")

STATUS_COLORS = {
    "Shortlisted":     "🔵",
    "Invited":         "📧",
    "In Progress":     "⏳",
    "Completed":       "✅",
    "Passed":          "🟢",
    "Below Threshold": "🔴",
    "Expired":         "⚫",
}

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match((email or "").strip()))


def _n8n_log_file() -> Path:
    return Path.home() / ".n8n" / "n8nEventLog.log"


def _normalize_n8n_error(message: str) -> str:
    msg = (message or "").strip()
    low = msg.casefold()
    if "authorization grant" in low or "refresh token" in low or "revoked" in low:
        return "n8n Gmail credential is invalid/expired. Reconnect Gmail in n8n and try again."
    if "cannot read properties of undefined" in low and "split" in low:
        return "n8n workflow received missing email data. Verify Gmail 'To' mapping from webhook payload."
    return msg or "n8n workflow failed"


def _detect_recent_n8n_failure(started_at_epoch: float) -> str | None:
    """Best-effort detection for webhook-accepted but downstream-failed n8n runs."""
    log_path = _n8n_log_file()
    if not log_path.exists():
        return None

    # n8n writes logs asynchronously; short polling catches immediate failures.
    for _ in range(6):
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-1200:]
        except Exception:
            return None

        recent_events = []
        for line in lines:
            try:
                evt = json.loads(line)
            except Exception:
                continue

            ts_raw = evt.get("ts")
            if not ts_raw:
                continue

            try:
                ts_epoch = datetime.fromisoformat(ts_raw).timestamp()
            except Exception:
                continue

            if ts_epoch >= started_at_epoch - 1.0:
                recent_events.append((ts_epoch, evt))

        if recent_events:
            started_ids = set()
            for _, evt in recent_events:
                if evt.get("eventName") != "n8n.workflow.started":
                    continue
                payload = evt.get("payload") or {}
                if payload.get("workflowName") != N8N_INVITE_WORKFLOW_NAME:
                    continue
                exec_id = str(payload.get("executionId") or "").strip()
                if exec_id:
                    started_ids.add(exec_id)

            for _, evt in recent_events:
                if evt.get("eventName") != "n8n.workflow.failed":
                    continue
                payload = evt.get("payload") or {}
                if payload.get("workflowName") != N8N_INVITE_WORKFLOW_NAME:
                    continue
                exec_id = str(payload.get("executionId") or "").strip()
                # Match either known started execution or a very recent failed execution.
                if exec_id and (exec_id in started_ids):
                    return _normalize_n8n_error(payload.get("errorMessage", ""))
                if not started_ids:
                    return _normalize_n8n_error(payload.get("errorMessage", ""))

        time.sleep(0.4)

    return None


def _is_strong_shortlist_candidate(candidate: dict, min_match_score: float = 7.0) -> bool:
    """Auto-select only strong JD matches with usable identity info."""
    score = float(candidate.get("match_score") or 0)
    name = (candidate.get("name") or "").strip().lower()
    email = (candidate.get("email") or "").strip()
    return score >= min_match_score and name not in ("", "unknown") and _is_valid_email(email)


# ── PDF Extraction ────────────────────────────────────────────────────────

def extract_pdf_text(file_bytes: bytes, filename: str) -> str:
    """Extract text from a PDF file. Returns empty string if extraction fails."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text.strip()
    except Exception as e:
        print(f"[jd_page] PDF extract failed for {filename}: {e}")
        return ""


# ── n8n Invite Trigger ────────────────────────────────────────────────────

def send_invite_via_n8n(
    name:       str,
    email:      str,
    username:   str,
    password:   str,
    job_title:  str,
    deadline:   str,
) -> tuple[bool, str]:
    """
    POST candidate credentials to n8n webhook.
    n8n then sends the Gmail invite email.
    Returns (success, message).
    """
    name = (name or "").strip()
    email = (email or "").strip()
    username = (username or "").strip()
    password = (password or "").strip()
    job_title = (job_title or "").strip()
    deadline = (deadline or "").strip()

    if not _is_valid_email(email):
        return False, "Invalid candidate email; invite not sent."
    if not username or not password:
        return False, "Missing username/password for invite payload."

    try:
        payload = {
            "name":       name,
            "email":      email,
            "username":   username,
            "password":   password,
            "job_title":  job_title,
            "login_url":  APP_URL,
            "deadline":   deadline,
        }

        started_at = time.time()
        response = requests.post(N8N_INVITE_WEBHOOK, json=payload, timeout=10)
        detail = response.text.strip()[:300] if response.text else "no response body"
        if not (200 <= response.status_code < 300):
            return False, f"HTTP {response.status_code}: {detail}"

        downstream_error = _detect_recent_n8n_failure(started_at)
        if downstream_error:
            return False, downstream_error

        return True, "Webhook accepted"
    except Exception as e:
        print(f"[jd_page] n8n webhook error for {email}: {e}")
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def show_jd_page():
    """Main entry point. Call this from recruiter_dashboard.py."""

    check_expired_invites()

    st.markdown("## 💼 Job Postings")

    tab1, tab2 = st.tabs(["➕ New Job Posting", "📋 Active Postings"])

    with tab1:
        _show_new_posting_tab()

    with tab2:
        _show_active_postings_tab()


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — NEW JOB POSTING
# ═══════════════════════════════════════════════════════════════════════════

def _show_new_posting_tab():
    """Upload JD + resumes, run matching, review shortlist, send invites."""

    st.markdown("### Step 1 — Job Details")

    col1, col2 = st.columns([2, 1])
    with col1:
        job_title = st.text_input(
            "Job Title *",
            placeholder="e.g. Python Backend Developer",
            key="jd_title",
        )
    with col2:
        min_pass_score = st.number_input(
            "Min Pass Score (out of 100)",
            min_value=0, max_value=100, value=60,
            key="jd_min_score",
            help="Candidates scoring above this after interview get reported to you",
        )
        shortlist_threshold = st.number_input(
            "Shortlist Match Threshold (/10)",
            min_value=0.0,
            max_value=10.0,
            value=7.0,
            step=0.5,
            key="jd_shortlist_threshold",
            help="Auto-select resumes at or above this JD match score",
        )

    jd_text = st.text_area(
        "Job Description *",
        placeholder="Paste the full job description here...",
        height=200,
        key="jd_text",
    )

    deadline_date = st.date_input(
        "Interview Deadline",
        min_value=date.today(),
        key="jd_deadline",
        help="Candidates must complete interview before this date",
    )

    st.markdown("---")
    st.markdown("### Step 2 — Upload Resumes")

    uploaded_files = st.file_uploader(
        "Upload resume PDFs (multiple allowed)",
        type=["pdf"],
        accept_multiple_files=True,
        key="jd_resumes",
    )

    if uploaded_files:
        st.caption(f"📁 {len(uploaded_files)} resume(s) uploaded")

    st.markdown("---")

    # ── Analyse Button ────────────────────────────────────────────────
    if st.button("🔍 Analyse Resumes", type="primary", use_container_width=True):

        if not job_title.strip():
            st.error("Please enter a job title.")
            return
        if not jd_text.strip():
            st.error("Please enter the job description.")
            return
        if not uploaded_files:
            st.error("Please upload at least one resume PDF.")
            return

        # Extract text from each PDF
        resumes = []
        with st.spinner("Extracting text from PDFs..."):
            for f in uploaded_files:
                text = extract_pdf_text(f.read(), f.name)
                resumes.append({"filename": f.name, "text": text})

        # Score all resumes vs JD
        progress_bar = st.progress(0, text="Scoring resumes with AI...")
        results = []

        for i, resume in enumerate(resumes):
            progress_bar.progress(
                (i + 1) / len(resumes),
                text=f"Scoring {resume['filename']} ({i+1}/{len(resumes)})..."
            )
            from matching_service.matcher import score_resume_vs_jd
            result = score_resume_vs_jd(resume["text"], jd_text)
            result["filename"] = resume["filename"]
            result["resume_text"] = resume["text"]
            result["row_id"] = f"{resume['filename']}::{i}"
            results.append(result)
            if i < len(resumes) - 1:
                time.sleep(0.6)

        # Sort by score
        results.sort(key=lambda x: x["match_score"], reverse=True)
        progress_bar.empty()

        # Store in session state for the review step below
        st.session_state.jd_match_results    = results
        st.session_state.jd_title_input      = job_title
        st.session_state.jd_text_input       = jd_text
        st.session_state.jd_min_score_input  = min_pass_score
        st.session_state.jd_deadline_input   = deadline_date
        st.session_state.jd_shortlist_threshold_input = float(shortlist_threshold)
        st.session_state.jd_selections       = {
            r["row_id"]: _is_strong_shortlist_candidate(
                r, st.session_state.jd_shortlist_threshold_input
            ) for r in results
        }

        st.success(f"✅ Scored {len(results)} resume(s). Review the shortlist below.")
        st.rerun()

    # ── Shortlist Review ──────────────────────────────────────────────
    if st.session_state.get("jd_match_results"):
        _show_shortlist_review()


def _show_shortlist_review():
    """Show ranked shortlist table with approve/exclude toggles."""

    results   = st.session_state.jd_match_results
    title     = st.session_state.jd_title_input
    deadline  = st.session_state.jd_deadline_input
    shortlist_threshold = float(st.session_state.get("jd_shortlist_threshold_input", 7.0))

    st.markdown("---")
    st.markdown("### Step 3 — Review Shortlist")
    st.caption("Uncheck candidates you want to exclude before sending invites.")
    st.caption("You can edit candidate name/email before invite send.")

    top1, top2 = st.columns([2, 1])
    with top1:
        shortlist_threshold = st.number_input(
            "Auto-select Threshold (/10)",
            min_value=0.0,
            max_value=10.0,
            step=0.5,
            value=shortlist_threshold,
            key="jd_shortlist_threshold_review",
            help="Candidates meeting this score and valid identity are selected by default",
        )
        st.session_state.jd_shortlist_threshold_input = float(shortlist_threshold)
    with top2:
        st.write("")
        if st.button("Apply Auto-Select Rule", use_container_width=True):
            for r in results:
                _k = r.get("row_id", r["filename"])
                st.session_state.jd_selections[_k] = _is_strong_shortlist_candidate(
                    r, st.session_state.jd_shortlist_threshold_input
                )
            st.rerun()

    auto_selected = sum(
        1 for r in results
        if _is_strong_shortlist_candidate(r, st.session_state.jd_shortlist_threshold_input)
    )
    if auto_selected < len(results):
        st.info(
            f"Auto-selected {auto_selected}/{len(results)} candidates "
            f"(rule: score >= {st.session_state.jd_shortlist_threshold_input:.1f} with valid name and email)."
        )

    # Column headers
    hcols = st.columns([0.5, 2.5, 1.3, 1, 3, 1])
    hcols[0].markdown("**Include**")
    hcols[1].markdown("**Candidate**")
    hcols[2].markdown("**File**")
    hcols[3].markdown("**Score**")
    hcols[4].markdown("**Reason**")
    hcols[5].markdown("**Gaps**")

    st.markdown("---")

    for r in results:
        key  = r.get("row_id", r["filename"])
        cols = st.columns([0.5, 2.5, 1.3, 1, 3, 1])

        # Checkbox
        checked = cols[0].checkbox(
            "", value=st.session_state.jd_selections.get(key, True),
            key=f"sel_{key}",
            label_visibility="collapsed",
        )
        st.session_state.jd_selections[key] = checked

        score = r["match_score"]
        emoji = "🟢" if score >= 7 else ("🟡" if score >= 5 else "🔴")

        name_key = f"cand_name_{key}"
        email_key = f"cand_email_{key}"

        if name_key not in st.session_state:
            st.session_state[name_key] = r.get("name", "")
        if email_key not in st.session_state:
            st.session_state[email_key] = r.get("email", "")

        edited_name = cols[1].text_input(
            f"Candidate Name {key}",
            key=name_key,
            label_visibility="collapsed",
            placeholder="Candidate name",
        ).strip()
        edited_email = cols[1].text_input(
            f"Candidate Email {key}",
            key=email_key,
            label_visibility="collapsed",
            placeholder="candidate@email.com",
        ).strip()

        r["name"] = edited_name or "Unknown"
        r["email"] = edited_email
        cols[2].caption(r["filename"])
        cols[3].markdown(f"{emoji} **{score}/10**")
        cols[4].caption(r["match_reason"])

        gaps = r.get("key_gaps", [])
        if gaps:
            cols[5].caption(", ".join(gaps[:2]))

    # Selected count
    selected = [
        r for r in results
        if st.session_state.jd_selections.get(r.get("row_id", r["filename"]), True)
    ]
    st.markdown(f"**{len(selected)} candidate(s) selected for invite**")

    st.markdown("---")

    # ── Send Invites Button ───────────────────────────────────────────
    if st.button(
        f"📧 Send Invites to {len(selected)} Candidate(s)",
        type="primary",
        use_container_width=True,
        disabled=len(selected) == 0,
    ):
        if len(selected) == 0:
            st.warning("No candidates selected.")
            return

        invalid_rows = []
        for r in selected:
            _name = (r.get("name") or "").strip()
            _email = (r.get("email") or "").strip()
            if (not _name) or (_name.lower() == "unknown") or (not _is_valid_email(_email)):
                invalid_rows.append(
                    f"{r.get('filename', 'resume')} -> name='{_name or 'missing'}', email='{_email or 'missing'}'"
                )

        if invalid_rows:
            st.error("Please correct name/email before sending invites.")
            for row in invalid_rows[:8]:
                st.caption(f"• {row}")
            return

        _send_invites(selected, title, st.session_state.jd_text_input,
                      st.session_state.jd_min_score_input, deadline)


def _send_invites(selected, job_title, jd_text, min_pass_score, deadline_date):
    """Create job posting, save profiles, create accounts, send emails."""

    deadline_dt = datetime.combine(deadline_date, datetime.max.time())

    # Step 1: Save job posting
    with st.spinner("Creating job posting..."):
        # Get recruiter email from DB
        from database import SessionLocal, User
        _db = SessionLocal()
        try:
            _recruiter = _db.query(User).filter_by(
                username=st.session_state.get("auth_username")
            ).first()
            _recruiter_email = _recruiter.email if _recruiter else None
        finally:
            _db.close()

        jd_id = save_job_posting(
            title           = job_title,
            jd_text         = jd_text,
            min_pass_score  = min_pass_score,
            deadline        = deadline_dt,
            recruiter_email = _recruiter_email,
        )

    progress = st.progress(0, text="Creating accounts and sending invites...")
    invite_sent_count = 0
    account_only_count = 0
    fail_count = 0
    results_log = []

    for i, r in enumerate(selected):
        progress.progress(
            (i + 1) / len(selected),
            text=f"Processing {r['name']} ({i+1}/{len(selected)})..."
        )

        try:
            # Step 2: Save candidate profile
            profile_id = save_candidate_profile(
                name            = r["name"],
                email           = r["email"],
                jd_id           = jd_id,
                resume_text     = r.get("resume_text", ""),
                resume_filename = r["filename"],
                match_score     = r["match_score"],
                match_reason    = r["match_reason"],
                key_matches     = r.get("key_matches", []),
                key_gaps        = r.get("key_gaps",    []),
            )

            # Step 3: Create student account
            account = create_candidate_account(profile_id)
            if "error" in account:
                fail_count += 1
                results_log.append({"name": r["name"], "status": "❌ Account creation failed"})
                continue

            username = account.get("username")
            password = account.get("password")
            if not username or not password:
                fail_count += 1
                results_log.append({
                    "name": r["name"],
                    "email": r["email"],
                    "status": "❌ Account exists but credentials unavailable",
                })
                continue

            # Safety gate: never email credentials unless they can authenticate now.
            auth_check = verify_login(username, password)
            if not auth_check or auth_check.get("role") != "student" or auth_check.get("username") != username:
                fail_count += 1
                results_log.append({
                    "name": r["name"],
                    "email": r.get("email"),
                    "username": username,
                    "password": password,
                    "status": "❌ Credential verification failed (not sent)",
                })
                continue

            email = (r.get("email") or "").strip()
            if not email or "@" not in email or email.lower().startswith("unknown@"):
                account_only_count += 1
                results_log.append({
                    "name": r["name"],
                    "email": email,
                    "username": username,
                    "password": password,
                    "status": "⚠️ Account created, invalid/missing email",
                })
                continue

            # Step 4: Send invite via n8n
            email_sent, email_error = send_invite_via_n8n(
                name      = r["name"],
                email     = email,
                username  = username,
                password  = password,
                job_title = job_title,
                deadline  = deadline_date.strftime("%d %b %Y"),
            )

            if email_sent:
                mark_invite_sent(profile_id)
                invite_sent_count += 1
                results_log.append({
                    "name":     r["name"],
                    "email":    email,
                    "username": username,
                    "password": password,
                    "status":   "✅ Invite sent",
                })
            else:
                # Email failed but account created — still log credentials
                account_only_count += 1
                results_log.append({
                    "name":     r["name"],
                    "email":    email,
                    "username": username,
                    "password": password,
                    "status":   f"⚠️ Account created, email failed ({email_error})",
                })

        except Exception as e:
            fail_count += 1
            results_log.append({"name": r["name"], "status": f"❌ Error: {str(e)}"})

    progress.empty()

    # ── Results Summary ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ✅ Invite Results")
    st.markdown(
        f"**{invite_sent_count} invite(s) sent** · "
        f"**{account_only_count} account(s) created (email not sent)** · "
        f"**{fail_count} failed** · "
        f"Job Posting ID: `{jd_id}`"
    )

    # Show credentials table (important if email failed)
    st.markdown("**Candidate Credentials** — Save this. Passwords shown once only.")

    for log in results_log:
        with st.container(border=True):
            cols = st.columns([2, 1.5, 1.5, 2])
            cols[0].markdown(f"**{log['name']}**  \n{log.get('email', '')}")
            cols[1].code(log.get("username", "—"))
            cols[2].code(log.get("password", "—"))
            cols[3].markdown(log["status"])

    # Clear session state for fresh start
    if st.button("➕ Create Another Job Posting", use_container_width=True):
        for key in ["jd_match_results", "jd_title_input", "jd_text_input",
                    "jd_min_score_input", "jd_deadline_input", "jd_selections",
                    "jd_shortlist_threshold_input", "jd_shortlist_threshold_review"]:
            st.session_state.pop(key, None)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — ACTIVE POSTINGS
# ═══════════════════════════════════════════════════════════════════════════

def _show_active_postings_tab():
    """Show all job postings with candidate status breakdown."""

    postings = get_all_job_postings()

    if not postings:
        st.info("No job postings yet. Create one in the 'New Job Posting' tab.")
        return

    for posting in postings:
        stats = get_jd_stats(posting.id)
        status_pill = "🟢 Active" if posting.status == "Active" else "⚫ Closed"
        deadline_str = posting.deadline.strftime("%d %b %Y") if posting.deadline else "No deadline"

        with st.container(border=True):
            # Header row
            h1, h2, h3 = st.columns([3, 1.5, 1])
            h1.markdown(f"### {posting.title}")
            h2.markdown(f"{status_pill}  ·  📅 {deadline_str}")
            h3.markdown(f"Min Score: **{posting.min_pass_score}/100**")

            # Stats row
            s1, s2, s3, s4, s5, s6 = st.columns(6)
            s1.metric("Total",           stats["total"])
            s2.metric("📧 Invited",      stats["Invited"])
            s3.metric("⏳ In Progress",  stats["In Progress"])
            s4.metric("🟢 Passed",       stats["Passed"])
            s5.metric("🔴 Below",        stats["Below Threshold"])
            s6.metric("⚫ Expired",      stats["Expired"])

            # Candidate list expander
            with st.expander(f"View {stats['total']} Candidate(s)"):
                candidates = get_candidates_by_jd(posting.id)

                if not candidates:
                    st.caption("No candidates yet.")
                else:
                    # Table header
                    th = st.columns([2.5, 1.5, 1, 1.5, 2])
                    th[0].markdown("**Name**")
                    th[1].markdown("**Email**")
                    th[2].markdown("**Match**")
                    th[3].markdown("**Status**")
                    th[4].markdown("**Username**")

                    for c in candidates:
                        sc = c.match_score or 0
                        emoji = "🟢" if sc >= 7 else ("🟡" if sc >= 5 else "🔴")
                        status_icon = STATUS_COLORS.get(c.interview_status, "❓")

                        row = st.columns([2.5, 1.5, 1, 1.5, 2])
                        row[0].markdown(f"**{c.name}**")
                        row[1].caption(c.email)
                        row[2].markdown(f"{emoji} {sc}/10")
                        row[3].markdown(f"{status_icon} {c.interview_status}")
                        row[4].code(c.username or "—")

            # Close posting button
            if posting.status == "Active":
                if st.button(
                    "Close Posting",
                    key=f"close_{posting.id}",
                    help="Mark this job as closed — no new interviews",
                ):
                    close_job_posting(posting.id)
                    st.success("Posting closed.")
                    st.rerun()