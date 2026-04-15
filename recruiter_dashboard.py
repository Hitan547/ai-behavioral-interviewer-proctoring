"""
recruiter_dashboard.py — Simplified & Reliable
Primary section navigation is horizontal in the main area; sidebar holds account tools.
"""

import html
import io
import json
import streamlit as st
import plotly.graph_objects as go
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from database import (
    get_all_sessions, get_session_by_id,
    update_candidate_status, save_recruiter_notes, get_all_users
)

# ─────────────────────────────────────────────
# COLORS
# ─────────────────────────────────────────────
C = {
    "primary":   "#1D9E75",
    "secondary": "#185FA5",
    "accent":    "#E8A020",
    "danger":    "#CC2222",
    "info":      "#4C9ED9",
    "surface":   "#FFFFFF",
    "border":    "#E0E4E8",
    "text":      "#1A1F36",
    "muted":     "#6B7280",
}

EMOTION_EMOJI = {
    "happy": "😊", "neutral": "😐", "sad": "😢",
    "angry": "😠", "fear": "😰", "surprise": "😲", "disgust": "😑",
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _score_emoji(s):
    return "🟢" if s >= 8 else ("🟡" if s >= 6 else ("🟠" if s >= 4 else "🔴"))

def _score_label(s):
    return "Excellent" if s >= 8 else ("Good" if s >= 6 else ("Average" if s >= 4 else "Needs Work"))

def _verdict_badge(v):
    return {"Strong Advance": "🟢 Strong Advance", "Advance": "🔵 Advance",
            "Borderline": "🟡 Borderline", "Do Not Advance": "🔴 Do Not Advance"}.get(v, v or "—")

def _verdict_from_score(cog):
    return ("Strong Advance" if cog >= 7.5 else
            "Advance" if cog >= 5.5 else
            "Borderline" if cog >= 3.5 else "Do Not Advance")

def _verdict_color(v):
    return {
        "Strong Advance": C["primary"], "Advance": C["secondary"],
        "Borderline": C["accent"],      "Do Not Advance": C["danger"],
    }.get(v, C["muted"])


def _safe_json_loads(raw_value, fallback):
    """Defensive JSON decode for historical/partial records."""
    if not raw_value:
        return fallback
    try:
        parsed = json.loads(raw_value)
        return fallback if parsed is None else parsed
    except Exception:
        return fallback


_STATUS_OPTIONS = ["Pending", "Shortlisted", "Rejected"]


def _status_index(value):
    """Return a stable index for status select controls."""
    try:
        return _STATUS_OPTIONS.index((value or "Pending"))
    except Exception:
        return 0


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def generate_candidate_pdf(session_id: int) -> bytes:
    s = get_session_by_id(session_id)
    if not s:
        return b""

    insight  = _safe_json_loads(s.insight_json, {})
    per_q    = _safe_json_loads(s.per_question_json, [])
    verdicts = _safe_json_loads(s.recruiter_verdicts_json, [])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm,  bottomMargin=20*mm)
    styles  = getSampleStyleSheet()
    title_s = ParagraphStyle("T",  parent=styles["Title"],   fontSize=20,
                              fontName="Helvetica-Bold",
                              textColor=colors.HexColor(C["primary"]), spaceAfter=4)
    h1_s    = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13,
                              fontName="Helvetica-Bold",
                              textColor=colors.HexColor(C["secondary"]), spaceAfter=5)
    h2_s    = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11,
                              fontName="Helvetica-Bold",
                              textColor=colors.HexColor(C["text"]), spaceAfter=4)
    body_s  = ParagraphStyle("B",  parent=styles["Normal"],  fontSize=9,
                              leading=13, spaceAfter=3)
    cap_s   = ParagraphStyle("C",  parent=styles["Normal"],  fontSize=8,
                              textColor=colors.HexColor(C["muted"]), spaceAfter=2)
    ans_s   = ParagraphStyle("A",  parent=styles["Normal"],  fontSize=9, leading=13,
                              backColor=colors.HexColor("#F0F4F8"), borderPad=5, spaceAfter=4)

    def hr():
        return HRFlowable(width="100%", thickness=0.5,
                          color=colors.HexColor(C["border"]), spaceAfter=8)
    def sp(h=6):
        return Spacer(1, h)

    sc      = s.final_score or 0
    avg_cog = s.cognitive_score or 5.0
    verdict = _verdict_from_score(avg_cog)
    vc      = _verdict_color(verdict)

    story = [
        Paragraph("PsySense AI Interview Platform", cap_s),
        Paragraph(f"Candidate Report: {s.candidate_name}", title_s),
        sp(2),
        Paragraph(
            f"Date: {s.created_at.strftime('%d %b %Y, %H:%M')}  |  "
            f"Questions: {s.questions_answered}  |  "
            f"{'JD-Scored' if s.jd_used else 'No JD'}  |  Session #{s.id}", cap_s),
        sp(6), hr(),
        Paragraph(
            f'<font color="{vc}"><b>Verdict: {verdict}</b></font> — '
            f'Score: <b>{sc}/100</b>  |  '
            f'Recommendation: <b>{insight.get("recommendation","N/A")}</b>', body_s),
        sp(8),
        Paragraph("Score Summary", h1_s),
    ]

    tbl = Table(
        [["Dimension", "Score", "Level"],
         ["Answer Quality", f"{round(s.cognitive_score or 5,1)}/10",
          _score_label(s.cognitive_score or 5)],
         ["Emotional Tone", f"{round(s.emotion_score or 5,1)}/10",
          _score_label(s.emotion_score or 5)],
         ["Attentiveness",  f"{round(s.engagement_score or 5,1)}/10",
          _score_label(s.engagement_score or 5)],
         ["Overall Score",  f"{sc}/100", ""]],
        colWidths=[90*mm, 40*mm, 40*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,0), colors.HexColor(C["secondary"])),
        ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
        ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.HexColor("#F7F9FC"), colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.4, colors.HexColor(C["border"])),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("FONTNAME",      (0,4),(-1,4),  "Helvetica-Bold"),
    ]))
    story += [tbl, sp(10)]

    if insight:
        story += [hr(), Paragraph("AI Recruiter Assessment", h1_s)]
        for item in insight.get("strengths", []):
            story.append(Paragraph(f"✓ {item}", body_s))
        for item in insight.get("weaknesses", []):
            story.append(Paragraph(f"⚠ {item}", body_s))
        if insight.get("recommendation"):
            story.append(Paragraph(
                f"<b>Recommendation:</b> {insight['recommendation']}", body_s))
        story.append(sp(10))

    if per_q:
        story += [hr(), Paragraph("Question-by-Question Breakdown", h1_s), sp(4)]
        DIM = {"clarity": "Clarity", "relevance": "Relevance", "star_quality": "STAR",
               "specificity": "Specificity", "communication": "Communication",
               "job_fit": "Job Fit"}
        for i, qd in enumerate(per_q):
            v_lbl = qd.get("verdict", verdicts[i] if i < len(verdicts) else "")
            story += [
                Paragraph(f"<b>Q{i+1}:</b> {qd.get('question','')}", h2_s),
                Paragraph(f"Verdict: <b>{v_lbl}</b>", cap_s) if v_lbl else sp(0),
                Paragraph(qd.get("answer") or "No answer recorded.", ans_s),
            ]
            qt = Table(
                [["Answer Quality", "Emotional Tone", "Attentiveness", "Face Visible"],
                 [f"{round(qd.get('cognitive',5),1)}/10",
                  f"{round(qd.get('emotion',5),1)}/10",
                  f"{round(qd.get('engagement',5),1)}/10",
                  f"{100 - qd.get('absence',0)*100:.0f}%"]],
                colWidths=[42*mm]*4)
            qt.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,0), colors.HexColor(C["info"])),
                ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
                ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,-1), 8),
                ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor(C["border"])),
                ("TOPPADDING",    (0,0),(-1,-1), 4),
                ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ]))
            story += [qt, sp(6), hr()]

    story.append(Paragraph(
        "PsySense AI — For internal recruiter use only. Confidential.", cap_s))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────
# MAIN DASHBOARD
# ─────────────────────────────────────────────
RECRUITER_NAV_OPTIONS = ["📋 Candidates", "💼 Jobs", "👥 Students", "📈 Analytics"]


def _recruiter_logout():
    st.session_state.clear()
    st.rerun()


def show_recruiter_dashboard():
    if "recruiter_nav" not in st.session_state:
        st.session_state.recruiter_nav = "📋 Candidates"

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&display=swap');
    html, body { font-family: 'DM Sans', sans-serif !important; }
    .stApp {
      background: #F0F4F8 !important;
      --stTextColor: #1a1f36 !important;
      --stHeadingColor: #111827 !important;
    }
    #MainMenu, footer, header { visibility: hidden; }

    /* Force readable text on light backgrounds (overrides dark theme tokens) */
    [data-testid="stSidebar"] {
      color: #1a1f36 !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] code {
      color: #1a1f36 !important;
    }
    [data-testid="stSidebar"] [data-testid="stCaption"],
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] small {
      color: #4b5563 !important;
    }
    [data-testid="stSidebar"] .stTextInput input {
      color: #1a1f36 !important;
      -webkit-text-fill-color: #1a1f36 !important;
    }

    section.main [data-testid="stMarkdownContainer"] p,
    section.main [data-testid="stMarkdownContainer"] span,
    section.main [data-testid="stMarkdownContainer"] strong,
    section.main [data-testid="stMarkdownContainer"] li,
    section.main [data-testid="stMarkdownContainer"] code {
      color: #1a1f36 !important;
    }
    section.main [data-testid="stCaption"] {
      color: #4b5563 !important;
    }
    section.main [data-baseweb="select"] span,
    section.main [data-baseweb="input"] input {
      color: #1a1f36 !important;
    }
    section.main [data-testid="stExpander"] p,
    section.main [data-testid="stExpander"] li,
    section.main [data-testid="stExpander"] summary {
      color: #1a1f36 !important;
    }
    section.main .stRadio [data-testid="stMarkdownContainer"] p,
    section.main .stRadio label,
    section.main [role="radiogroup"] label,
    section.main [data-baseweb="radio"] label {
      color: #1a1f36 !important;
    }

    /* Primary content uses stMain — do NOT set color on stMain root (breaks primary button labels) */
    [data-testid="stMain"] [data-testid="stMarkdownContainer"],
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] span,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] em,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] code {
      color: #111827 !important;
    }
    [data-testid="stMain"] [data-testid="stCaption"],
    [data-testid="stMain"] [data-testid="stCaption"] p,
    [data-testid="stMain"] div[data-testid="stCaption"] {
      color: #374151 !important;
    }
    [data-testid="stMain"] [data-testid="stExpander"] p,
    [data-testid="stMain"] [data-testid="stExpander"] li,
    [data-testid="stMain"] [data-testid="stExpander"] summary {
      color: #111827 !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] p,
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] span,
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaption"],
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaption"] p {
      color: #111827 !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stCaption"] {
      color: #374151 !important;
    }
    [data-testid="stMain"] [data-baseweb="select"] div[role="combobox"],
    [data-testid="stMain"] [data-baseweb="select"] span {
      color: #111827 !important;
    }
    [data-testid="stMain"] h1,
    [data-testid="stMain"] h2,
    [data-testid="stMain"] h3 {
      color: #111827 !important;
    }

    /* Jobs / forms: primary buttons must stay white-on-dark (Analyse Resumes, etc.) */
    [data-testid="stMain"] .stButton > button[kind="primary"],
    [data-testid="stMain"] button[kind="primary"],
    [data-testid="stMain"] .stFormSubmitButton > button[kind="primary"],
    [data-testid="stMain"] [data-testid="stFormSubmitButton"] button[kind="primary"] {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }
    [data-testid="stMain"] .stButton > button[kind="primary"] p,
    [data-testid="stMain"] .stButton > button[kind="primary"] span,
    [data-testid="stMain"] button[kind="primary"] p,
    [data-testid="stMain"] button[kind="primary"] span {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }
    /* st.tabs (Job Postings) */
    [data-testid="stMain"] [data-baseweb="tab"] {
      color: #4b5563 !important;
    }
    [data-testid="stMain"] [data-baseweb="tab"][aria-selected="true"] {
      color: #111827 !important;
      font-weight: 600 !important;
    }

    .ps-topbar {
        background: linear-gradient(120deg, #185FA5 0%, #1D9E75 100%);
        padding: 14px 24px; border-radius: 12px; margin-bottom: 16px;
    }
    .ps-topbar h2 { color: #fff !important; margin: 0; font-size: 20px; }
    .ps-topbar p  { color: rgba(255,255,255,0.8) !important; margin: 2px 0 0; font-size: 12px; }

    [data-testid="stMetric"] {
        background: #fff !important; border: 1px solid #E0E4E8 !important;
        border-radius: 10px !important; padding: 14px 16px !important;
    }
    [data-testid="stMetricValue"] > div {
        font-size: 24px !important; font-weight: 700 !important;
        color: #111827 !important;
    }
    [data-testid="stMetricLabel"] > div {
        font-size: 11px !important; font-weight: 600 !important;
        text-transform: uppercase !important; color: #6B7280 !important;
    }
    [data-testid="stDownloadButton"] > button {
        background: rgba(24,95,165,0.12) !important;
        border: 1.5px solid rgba(24,95,165,0.35) !important;
        color: #185FA5 !important; border-radius: 8px !important;
        font-weight: 600 !important;
    }
    [data-testid="stDownloadButton"] > button:hover {
        background: #185FA5 !important; color: #fff !important;
    }
    .vbadge { display:inline-block; padding:3px 11px; border-radius:20px;
               font-size:12px; font-weight:700; }
    .vb-green  { background:#1D9E7515; color:#1D9E75; border:1px solid #1D9E7540; }
    .vb-blue   { background:#185FA515; color:#185FA5; border:1px solid #185FA540; }
    .vb-yellow { background:#E8A02015; color:#E8A020; border:1px solid #E8A02050; }
    .vb-red    { background:#CC222215; color:#CC2222; border:1px solid #CC222240; }
    </style>
    """, unsafe_allow_html=True)

    # ── SIDEBAR — plan/usage before logout; single log out at bottom
    with st.sidebar:
        st.markdown("## 🏢 PsySense")
        st.caption(f"@{st.session_state.auth_username}")
        st.markdown("---")
        if st.session_state.get("recruiter_detail_id"):
            if st.button("← Back to List", use_container_width=True, key="sb_back_list"):
                st.session_state.recruiter_detail_id = None
                st.rerun()

        st.markdown("**📧 Notification email**")
        from database import SessionLocal, User
        _db = SessionLocal()
        try:
            _me = _db.query(User).filter_by(
                username=st.session_state.auth_username).first()
            _cur_email = _me.email or "" if _me else ""
            _org_id = _me.org_id if _me else None
        finally:
            _db.close()

        # Recover org context if session was started from a non-SaaS login path.
        if _org_id and not st.session_state.get("org_id"):
            st.session_state.org_id = _org_id

        new_email = st.text_input("Email", value=_cur_email,
                                  placeholder="you@email.com",
                                  key="recruiter_email_input",
                                  label_visibility="collapsed")
        if st.button("💾 Save email", use_container_width=True, key="save_email_btn"):
            _db2 = SessionLocal()
            try:
                _u = _db2.query(User).filter_by(
                    username=st.session_state.auth_username).first()
                if _u:
                    _u.email = new_email.strip()
                    _db2.commit()
                    st.success("✅ Saved")
            finally:
                _db2.close()

        # Keep critical actions visible near the top so they don't disappear below the fold.
        st.markdown("**⚙️ Account Actions**")
        can_open_billing = bool(st.session_state.get("org_id"))
        sidebar_action = st.selectbox(
            "Account action",
            ["No action", "Open Billing & Plan", "Log out"],
            key="sidebar_account_action_select",
            label_visibility="collapsed",
        )
        last_sidebar_action = st.session_state.get("_last_sidebar_action", "No action")
        if sidebar_action != last_sidebar_action:
            st.session_state["_last_sidebar_action"] = sidebar_action
            if sidebar_action == "Open Billing & Plan":
                if can_open_billing:
                    st.session_state.show_billing_page = True
                    st.rerun()
                else:
                    st.warning("Billing is unavailable because this account has no organization.")
            elif sidebar_action == "Log out":
                _recruiter_logout()

        if not st.session_state.get("org_id"):
            st.caption("Billing is available after recruiter signup creates an organization.")

        if st.session_state.get("org_id"):
            from saas.saas_auth import show_saas_billing_sidebar
            show_saas_billing_sidebar(st.session_state.org_id)

        st.markdown("---")

    # ── TOP BAR (full width) ──
    st.markdown("""
    <div class="ps-topbar">
        <h2>🏢 PsySense — Recruiter Intelligence Dashboard</h2>
        <p>AI-powered interview analysis platform</p>
    </div>
    """, unsafe_allow_html=True)

    # One-click logout outside Account Actions (select-driven to avoid hidden buttons).
    st.markdown("**Session**")
    logout_action = st.selectbox(
        "Session action",
        ["Stay logged in", "Logout now"],
        key="logout_direct_select",
        label_visibility="collapsed",
    )
    last_logout_action = st.session_state.get("_last_logout_action", "Stay logged in")
    if logout_action != last_logout_action:
        st.session_state["_last_logout_action"] = logout_action
        if logout_action == "Logout now":
            _recruiter_logout()

    # Duplicate critical actions in the main area to avoid sidebar visibility issues.
    st.markdown("**Quick Actions**")
    main_action = st.selectbox(
        "Quick action",
        ["No action", "Open Billing & Plan", "Log out"],
        key="main_quick_action_select",
        label_visibility="collapsed",
    )
    last_main_action = st.session_state.get("_last_main_action", "No action")
    if main_action != last_main_action:
        st.session_state["_last_main_action"] = main_action
        if main_action == "Open Billing & Plan":
            if bool(st.session_state.get("org_id")):
                st.session_state.show_billing_page = True
                st.rerun()
            else:
                st.warning("Billing is unavailable because this account has no organization.")
        elif main_action == "Log out":
            _recruiter_logout()

    _org = st.session_state.get("org_id")
    if st.session_state.get("show_billing_page") and not _org:
        st.session_state.show_billing_page = False
    if st.session_state.get("show_billing_page") and _org:
        b1, b2 = st.columns([1, 4])
        with b1:
            billing_nav = st.selectbox(
                "Billing navigation",
                ["Stay on billing", "Back to dashboard"],
                key="billing_nav_select",
                label_visibility="collapsed",
            )
            last_billing_nav = st.session_state.get("_last_billing_nav", "Stay on billing")
            if billing_nav != last_billing_nav:
                st.session_state["_last_billing_nav"] = billing_nav
                if billing_nav == "Back to dashboard":
                    st.session_state.show_billing_page = False
                    st.rerun()
        with b2:
            st.caption("Manage your subscription and usage.")
        try:
            from saas.saas_billing import show_billing_page
            show_billing_page(_org)
        except Exception as e:
            st.error(f"Billing is temporarily unavailable: {e}")
        return

    _idx = (
        RECRUITER_NAV_OPTIONS.index(st.session_state.recruiter_nav)
        if st.session_state.recruiter_nav in RECRUITER_NAV_OPTIONS else 0
    )
    main_nav = st.radio(
        "Section",
        RECRUITER_NAV_OPTIONS,
        horizontal=True,
        index=_idx,
        label_visibility="collapsed",
    )
    if main_nav != st.session_state.recruiter_nav:
        st.session_state.recruiter_nav = main_nav
        st.session_state.recruiter_detail_id = None
        st.rerun()

    # ── ROUTING ──
    detail_id = st.session_state.get("recruiter_detail_id")
    nav_mode  = st.session_state.recruiter_nav

    if detail_id:
        _show_candidate_detail(detail_id)
    elif nav_mode == "📋 Candidates":
        _show_overview()
    elif nav_mode == "💼 Jobs":
        from recruiter_jd_page import show_jd_page
        show_jd_page()
    elif nav_mode == "👥 Students":
        _show_registered_students()
    elif nav_mode == "📈 Analytics":
        _show_analytics()


# ─────────────────────────────────────────────
# CANDIDATES OVERVIEW
# ─────────────────────────────────────────────
def _show_overview():
    sessions = get_all_sessions()
    if not sessions:
        st.info("🎤 No interviews yet. Candidates appear here after completing an interview.")
        return

    total       = len(sessions)
    avg_s       = round(sum(s.final_score or 0 for s in sessions) / total, 1)
    passed      = sum(1 for s in sessions if (s.final_score or 0) >= 55)
    flagged     = sum(1 for s in sessions if s.flagged)
    shortlisted = sum(1 for s in sessions if s.status == "Shortlisted")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("👥 Total",       total)
    c2.metric("📊 Avg Score",   f"{avg_s}/100")
    c3.metric("✅ Pass Rate",   f"{round(passed/total*100,1)}%")
    c4.metric("🚩 Flagged",     flagged)
    c5.metric("⭐ Shortlisted", shortlisted)

    st.markdown("---")

    col_s, col_f, col_sort = st.columns([3, 2, 2])
    with col_s:
        search = st.text_input("Search", placeholder="🔍 Search by name...",
                               label_visibility="collapsed")
    with col_f:
        status_filter = st.selectbox("Status",
                                     ["All", "Pending", "Shortlisted", "Rejected"],
                                     label_visibility="collapsed")
    with col_sort:
        sort_by = st.selectbox("Sort",
                               ["Date ↓", "Score ↓", "Score ↑", "Name A-Z"],
                               label_visibility="collapsed")

    filtered = list(sessions)
    if search.strip():
        filtered = [s for s in filtered if search.lower() in s.candidate_name.lower()]
    if status_filter != "All":
        filtered = [s for s in filtered if s.status == status_filter]
    sort_map = {
        "Score ↓":  lambda s: -(s.final_score or 0),
        "Score ↑":  lambda s:  (s.final_score or 0),
        "Name A-Z": lambda s:   s.candidate_name.lower(),
    }
    if sort_by in sort_map:
        filtered.sort(key=sort_map[sort_by])

    st.markdown(
        f'<p style="color:#111827;font-weight:600;font-size:15px;margin:0 0 10px 0">'
        f"{len(filtered)} candidate(s)</p>",
        unsafe_allow_html=True,
    )

    STATUS_ICON = {"Pending": "🕐", "Shortlisted": "⭐", "Rejected": "❌"}
    BADGE_CLASS = {"Strong Advance": "vb-green", "Advance": "vb-blue",
                   "Borderline": "vb-yellow",    "Do Not Advance": "vb-red"}

    for s in filtered:
        sc      = s.final_score or 0
        emoji   = "🟢" if sc >= 75 else ("🟡" if sc >= 55 else "🔴")
        verdict = _verdict_from_score(s.cognitive_score or 5.0)
        bc      = BADGE_CLASS.get(verdict, "vb-yellow")
        si      = STATUS_ICON.get(s.status, "")
        insight_data = _safe_json_loads(s.insight_json, {})

        with st.container(border=True):
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2.5, 0.8, 0.7, 0.7, 0.7, 1.2, 1.0])
            nm = html.escape(s.candidate_name or "")
            un = html.escape(s.username or "—")
            stt = html.escape(s.status or "")
            c1.markdown(
                f'<p style="color:#111827;margin:0;line-height:1.45">'
                f"<strong>{nm}</strong><br/>"
                f'<code style="color:#334155;background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:12px">{un}</code>'
                f' <span style="color:#374151">· {si} {stt}</span></p>',
                unsafe_allow_html=True,
            )
            c2.markdown(
                f'<p style="color:#111827;margin:0;font-size:15px">{emoji} <strong>{sc}</strong></p>',
                unsafe_allow_html=True,
            )
            c3.markdown(
                f'<p style="color:#374151;font-size:13px;margin:0">🧠 {round(s.cognitive_score or 0, 1)}</p>',
                unsafe_allow_html=True,
            )
            c4.markdown(
                f'<p style="color:#374151;font-size:13px;margin:0">😊 {round(s.emotion_score or 0, 1)}</p>',
                unsafe_allow_html=True,
            )
            c5.markdown(
                f'<p style="color:#374151;font-size:13px;margin:0">👁 {round(s.engagement_score or 0, 1)}</p>',
                unsafe_allow_html=True,
            )
            c6.markdown(
                f'<span class="vbadge {bc}">{_verdict_badge(verdict)}</span>',
                unsafe_allow_html=True)
            c7.markdown(
                f'<p style="color:#374151;font-size:12px;margin:0">'
                f"{html.escape(s.created_at.strftime('%d %b %Y'))}</p>",
                unsafe_allow_html=True,
            )

            b1, b2, b3 = st.columns([1.5, 1, 1])
            with b1:
                if st.button("📄 Full Report", key=f"view_{s.id}"):
                    st.session_state.recruiter_detail_id = s.id
                    st.rerun()
            with b2:
                st.download_button(
                    "⬇ PDF", data=generate_candidate_pdf(s.id),
                    file_name=f"psysense_{s.candidate_name.replace(' ','_')}_{s.id}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{s.id}", use_container_width=True)
            with b3:
                if st.button("🚩 Flag", key=f"flag_{s.id}"):
                    st.info("Flagged for review")

            if insight_data.get("recommendation") or insight_data.get("strengths"):
                with st.expander("🎯 AI Insight"):
                    rec = insight_data.get("recommendation", "")
                    if rec:
                        st.info(f"**Recommendation:** {rec}")
                    ic1, ic2 = st.columns(2)
                    with ic1:
                        for item in insight_data.get("strengths", []):
                            st.caption(f"✅ {item}")
                    with ic2:
                        for item in insight_data.get("weaknesses", []):
                            st.caption(f"⚠️ {item}")

    if total >= 3:
        st.markdown("---")
        st.markdown("### 📊 Score Distribution")
        score_vals = [s.final_score or 0 for s in sessions]
        buckets = [
            ("<35\nNeeds Work", sum(1 for v in score_vals if v < 35)),
            ("35-55\nAverage",  sum(1 for v in score_vals if 35 <= v < 55)),
            ("55-75\nGood",     sum(1 for v in score_vals if 55 <= v < 75)),
            ("75+\nStrong",     sum(1 for v in score_vals if v >= 75)),
        ]
        fig = go.Figure(go.Bar(
            x=[b[0] for b in buckets], y=[b[1] for b in buckets],
            marker_color=[C["danger"], C["accent"], C["info"], C["primary"]],
            text=[b[1] for b in buckets], textposition="outside"))
        fig.update_layout(height=300, showlegend=False,
                          plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=20, b=40))
        st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
# CANDIDATE DETAIL
# ─────────────────────────────────────────────
def _show_candidate_detail(session_id: int):
    s = get_session_by_id(session_id)
    if not s:
        st.error("❌ Candidate not found.")
        return

    insight  = _safe_json_loads(s.insight_json, {})
    per_q    = _safe_json_loads(s.per_question_json, [])
    verdicts = _safe_json_loads(s.recruiter_verdicts_json, [])

    sc      = s.final_score or 0
    verdict = _verdict_from_score(s.cognitive_score or 5.0)
    vc      = _verdict_color(verdict)

    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown(f"## 📋 {s.candidate_name}")
        st.caption(
            f"📅 {s.created_at.strftime('%d %b %Y, %H:%M')} · "
            f"🎤 {s.questions_answered} questions · "
            f"{'JD ✓' if s.jd_used else 'No JD'} · ID #{s.id}")
    with h2:
        st.download_button(
            "⬇ PDF", data=generate_candidate_pdf(session_id),
            file_name=f"psysense_{s.candidate_name.replace(' ','_')}_{s.id}.pdf",
            mime="application/pdf",
            key=f"pdf_detail_{session_id}", use_container_width=True)

    st.markdown(f"""
    <div style="background:{vc}15;border-left:4px solid {vc};
         padding:14px 18px;border-radius:10px;margin:12px 0">
      <b style="color:{vc};font-size:16px">{_verdict_badge(verdict)}</b><br>
      <span style="color:#444;font-size:14px">
        Score: <b>{sc}/100</b> &nbsp;|&nbsp;
        Recommendation: <b>{insight.get("recommendation","N/A")}</b>
      </span>
    </div>
    """, unsafe_allow_html=True)

    g1, g2 = st.columns(2)
    with g1:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=sc,
            title={"text": "Overall Score"},
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": vc},
                   "steps": [{"range": [0,35],   "color": "#fee2e2"},
                              {"range": [35,55],  "color": "#fef9c3"},
                              {"range": [55,75],  "color": "#dbeafe"},
                              {"range": [75,100], "color": "#dcfce7"}],
                   "borderwidth": 0}))
        fig_gauge.update_layout(height=280,
                                margin=dict(l=20, r=20, t=40, b=10),
                                paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_gauge, use_container_width=True)

    with g2:
        fig_bar = go.Figure(go.Bar(
            x=["Answer Quality", "Emotional Tone", "Attentiveness"],
            y=[s.cognitive_score or 5, s.emotion_score or 5, s.engagement_score or 5],
            marker_color=[C["info"], C["accent"], C["primary"]],
            text=[f"{round(s.cognitive_score or 5,1)}/10",
                  f"{round(s.emotion_score or 5,1)}/10",
                  f"{round(s.engagement_score or 5,1)}/10"],
            textposition="outside"))
        fig_bar.update_layout(
            title="Signal Breakdown (/10)", yaxis=dict(range=[0, 12]),
            height=280, showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    with st.expander("⚙️ Recruiter Actions", expanded=True):
        a1, a2 = st.columns([1, 2])
        with a1:
            new_status = st.selectbox(
                "Status", _STATUS_OPTIONS,
                index=_status_index(s.status),
                key=f"status_{session_id}")
            if st.button("Update Status", key=f"upd_{session_id}",
                        use_container_width=True):
                update_candidate_status(session_id, new_status)

                if new_status == "Shortlisted":
                    import bcrypt
                    import secrets
                    import string
                    from database import (
                        SessionLocal,
                        User,
                        create_candidate_account,
                        get_profile_by_username,
                        mark_invite_sent,
                        verify_login,
                    )
                    try:
                        from recruiter_jd_page import send_invite_via_n8n
                    except Exception as invite_import_err:
                        send_invite_via_n8n = None
                        print(
                            "[n8n] ⚠️ Invite sender unavailable during import: "
                            f"{invite_import_err}",
                            flush=True,
                        )

                    _db = SessionLocal()
                    try:
                        _candidate_user = _db.query(User).filter_by(
                            username=s.username).first()
                        if not _candidate_user:
                            st.warning("Status updated but email notification failed: student account not found.")
                            print(f"[n8n] ⚠️ Invite skipped: student account missing for {s.username}", flush=True)
                        else:
                            candidate_email = (_candidate_user.email or "").strip()
                            if not candidate_email or "@" not in candidate_email:
                                st.warning(
                                    "Status updated but email notification failed: "
                                    "candidate email is missing or invalid."
                                )
                                print(
                                    f"[n8n] ⚠️ Invite skipped: invalid email for {s.username} -> {candidate_email}",
                                    flush=True,
                                )
                            else:
                                invite_username = _candidate_user.username
                                invite_password = None
                                can_send_invite = True
                                profile_id = None

                                # Prefer existing invite credentials when a candidate profile exists.
                                profile = get_profile_by_username(s.username)
                                if profile:
                                    profile_id = profile.id
                                    account = create_candidate_account(profile.id)
                                    if "error" in account:
                                        can_send_invite = False
                                        st.warning(
                                            "Status updated but email notification failed: "
                                            f"{account['error']}"
                                        )
                                        print(
                                            f"[n8n] ⚠️ Invite skipped for {candidate_email}: {account['error']}",
                                            flush=True,
                                        )
                                    else:
                                        invite_username = account.get("username") or invite_username
                                        invite_password = account.get("password")

                                # Session-only candidates have no reversible password; rotate to a fresh one.
                                if can_send_invite and not invite_password:
                                    alphabet = string.ascii_letters + string.digits
                                    invite_password = "".join(secrets.choice(alphabet) for _ in range(10))
                                    _candidate_user.password_hash = bcrypt.hashpw(
                                        invite_password.encode(),
                                        bcrypt.gensalt(),
                                    ).decode()
                                    _db.commit()

                                if can_send_invite:
                                    auth_check = verify_login(invite_username, invite_password)
                                    if (
                                        not auth_check
                                        or auth_check.get("role") != "student"
                                        or auth_check.get("username") != invite_username
                                    ):
                                        can_send_invite = False
                                        st.warning(
                                            "Status updated but email notification failed: "
                                            "generated credentials could not be verified."
                                        )
                                        print(
                                            f"[n8n] ⚠️ Invite skipped for {candidate_email}: credential verification failed",
                                            flush=True,
                                        )

                                if can_send_invite and send_invite_via_n8n is None:
                                    can_send_invite = False
                                    st.warning(
                                        "Status updated but email notification failed: "
                                        "invite sender is unavailable in this runtime."
                                    )

                                if can_send_invite:
                                    email_sent, email_error = send_invite_via_n8n(
                                        name=s.candidate_name,
                                        email=candidate_email,
                                        username=invite_username,
                                        password=invite_password,
                                        job_title="AI Mock Interview",
                                        deadline="Within 48 hours",
                                    )

                                    if email_sent:
                                        if profile_id:
                                            try:
                                                mark_invite_sent(profile_id)
                                            except Exception as mark_err:
                                                print(f"[n8n] ⚠️ Invite sent but mark_invite_sent failed: {mark_err}", flush=True)
                                        print(f"[n8n] ✅ Invite sent for {invite_username}", flush=True)
                                        st.success(f"✅ Status updated + invite sent to {candidate_email}")
                                    else:
                                        print(
                                            f"[n8n] ⚠️ Invite webhook failed for {candidate_email}: {email_error}",
                                            flush=True,
                                        )
                                        st.warning(f"Status updated but email notification failed: {email_error}")
                    finally:
                        _db.close()
                else:
                    st.success(f"✅ Updated to {new_status}")

                st.rerun()
        with a2:
            notes = st.text_area(
                "Recruiter Notes", value=s.recruiter_notes or "",
                placeholder="Private notes...",
                key=f"notes_{session_id}", height=90)
            if st.button("💾 Save Notes", key=f"save_{session_id}",
                         use_container_width=True):
                save_recruiter_notes(session_id, notes)
                st.success("✅ Saved")

    if insight:
        st.markdown("---")
        st.markdown("### 🎯 AI Assessment")
        i1, i2 = st.columns(2)
        with i1:
            st.markdown("**✅ Strengths**")
            for item in insight.get("strengths", []):
                st.success(f"→ {item}")
        with i2:
            st.markdown("**⚠️ Areas to Improve**")
            for item in insight.get("weaknesses", []):
                st.warning(f"→ {item}")
        if insight.get("recommendation"):
            st.info(f"**Hiring Recommendation:** {insight['recommendation']}")

    if per_q:
        st.markdown("---")
        st.markdown("### 📈 Score Trend")
        qlabels = [f"Q{i+1}" for i in range(len(per_q))]
        fig_t = go.Figure()
        for name, key, color in [
            ("Answer Quality", "cognitive",  C["info"]),
            ("Emotional Tone", "emotion",    C["accent"]),
            ("Attentiveness",  "engagement", C["primary"]),
        ]:
            fig_t.add_trace(go.Scatter(
                x=qlabels, y=[q.get(key, 5) for q in per_q],
                mode="lines+markers", name=name,
                line=dict(color=color, width=2.5),
                marker=dict(size=8)))
        fig_t.update_layout(
            yaxis=dict(range=[0, 10], title="Score /10"),
            height=280, hovermode="x unified",
            legend=dict(orientation="h", y=-0.25),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(b=60))
        st.plotly_chart(fig_t, use_container_width=True)

        st.markdown("---")
        st.markdown("### Question Breakdown")
        DIM = {"clarity": "Clarity", "relevance": "Relevance",
               "star_quality": "STAR", "specificity": "Specificity",
               "communication": "Communication", "job_fit": "Job Fit"}

        for i, qd in enumerate(per_q):
            v_lbl = qd.get("verdict", verdicts[i] if i < len(verdicts) else "")
            with st.expander(
                    f"Q{i+1}: {qd.get('question','')} — {_verdict_badge(v_lbl)}"):
                st.markdown("**Answer:**")
                st.info(qd.get("answer") or "_No answer recorded._")

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Answer Quality", f"{round(qd.get('cognitive',5),1)}/10")
                m2.metric("Emotional Tone", f"{round(qd.get('emotion',5),1)}/10")
                m3.metric("Attentiveness",  f"{round(qd.get('engagement',5),1)}/10")
                m4.metric("Face Visible",   f"{100-qd.get('absence',0)*100:.0f}%")

                dims = qd.get("dimensions", {})
                if dims:
                    st.markdown("**Dimension Scores**")
                    d_items = [(k, v) for k, v in dims.items()
                               if k in DIM and isinstance(v, (int, float))]
                    if d_items:
                        dc = st.columns(3)
                        for j, (dim, val) in enumerate(d_items):
                            dc[j % 3].metric(DIM[dim], f"{val}/10")
                    if dims.get("summary"):
                        st.caption(f"💬 {dims['summary']}")
                    kc, ic = st.columns(2)
                    if dims.get("key_strength"):
                        kc.success(f"✅ {dims['key_strength']}")
                    if dims.get("key_improvement"):
                        ic.warning(f"⚠️ {dims['key_improvement']}")

                sb = qd.get("speech", {})
                if sb:
                    st.markdown("**🎙️ Speech**")
                    s1, s2, s3 = st.columns(3)
                    s1.metric("Emotion",     f"{sb.get('emotion_model',5)}/10")
                    s2.metric("Fluency",      f"{sb.get('fluency_score',5)}/10")
                    s3.metric("Voice Energy", f"{sb.get('voice_score',5)}/10")
                    if sb.get("dominant_emotion"):
                        st.caption(
                            f"Dominant: **{sb['dominant_emotion'].capitalize()}**")

                fe = qd.get("facial_emotion", {})
                if fe and fe.get("breakdown"):
                    dominant = fe.get("dominant", "neutral")
                    label_map = {
                        "happy": "Confident", "neutral": "Composed",
                        "surprise": "Off guard", "fear": "Nervous",
                        "sad": "Low energy", "angry": "Stressed",
                        "disgust": "Uncomfortable",
                    }
                    st.markdown(
                        f"**😶 Facial Emotion:** "
                        f"{EMOTION_EMOJI.get(dominant,'😐')} "
                        f"{label_map.get(dominant, dominant.capitalize())}")


# ─────────────────────────────────────────────
# STUDENTS
# ─────────────────────────────────────────────
def _show_registered_students():
    st.markdown("### 👥 Registered Students")
    users = get_all_users()
    if not users:
        st.info("No student accounts registered yet.")
        return

    sessions = get_all_sessions()
    sc_map = {}
    for s in sessions:
        if s.username:
            sc_map[s.username] = sc_map.get(s.username, 0) + 1

    for u in users:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(
                f"**{u.display_name or u.username}**  \n`{u.username}`")
            c2.metric("Interviews", sc_map.get(u.username, 0))
            c3.caption(u.created_at.strftime("%d %b %Y"))


# ─────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────
def _show_analytics():
    st.markdown("### 📈 Advanced Analytics")
    sessions = get_all_sessions()
    if not sessions:
        st.info("No data yet.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Cognitive Score Distribution")
        fig = go.Figure(go.Histogram(
            x=[s.cognitive_score or 5 for s in sessions], nbinsx=8,
            marker_color=C["info"]))
        fig.update_layout(height=280, showlegend=False,
                          xaxis_title="Score /10", yaxis_title="Count",
                          plot_bgcolor="rgba(0,0,0,0)",
                          paper_bgcolor="rgba(0,0,0,0)",
                          margin=dict(t=10, b=30))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("#### Overall Score Distribution")
        fig2 = go.Figure(go.Histogram(
            x=[s.final_score or 0 for s in sessions], nbinsx=10,
            marker_color=C["primary"]))
        fig2.update_layout(height=280, showlegend=False,
                           xaxis_title="Score /100", yaxis_title="Count",
                           plot_bgcolor="rgba(0,0,0,0)",
                           paper_bgcolor="rgba(0,0,0,0)",
                           margin=dict(t=10, b=30))
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Average Signal Comparison")
    n = len(sessions)
    signals = {
        "Answer Quality": sum(s.cognitive_score  or 0 for s in sessions) / n,
        "Emotional Tone": sum(s.emotion_score    or 0 for s in sessions) / n,
        "Attentiveness":  sum(s.engagement_score or 0 for s in sessions) / n,
    }
    fig3 = go.Figure(go.Bar(
        x=list(signals.keys()), y=list(signals.values()),
        marker_color=[C["info"], C["accent"], C["primary"]],
        text=[f"{v:.1f}/10" for v in signals.values()],
        textposition="outside"))
    fig3.update_layout(yaxis=dict(range=[0, 10], title="Avg /10"),
                       height=300, showlegend=False,
                       plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)",
                       margin=dict(t=10, b=30))
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")
    st.markdown("#### Verdict Breakdown")
    vc = {"Strong Advance": 0, "Advance": 0,
          "Borderline": 0,    "Do Not Advance": 0}
    for s in sessions:
        v = _verdict_from_score(s.cognitive_score or 5.0)
        vc[v] = vc.get(v, 0) + 1

    fig4 = go.Figure(go.Pie(
        labels=list(vc.keys()), values=list(vc.values()),
        marker_colors=[C["primary"], C["secondary"], C["accent"], C["danger"]],
        hole=0.4))
    fig4.update_layout(height=300, margin=dict(t=10, b=10),
                       paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig4, use_container_width=True)


if __name__ == "__main__":
    show_recruiter_dashboard()