"""
recruiter_dashboard.py — Simplified & Reliable
Primary section navigation is horizontal in the main area; sidebar holds account tools.
"""

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


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def generate_candidate_pdf(session_id: int) -> bytes:
    s = get_session_by_id(session_id)
    if not s:
        return b""

    insight  = json.loads(s.insight_json)           if s.insight_json           else {}
    per_q    = json.loads(s.per_question_json)       if s.per_question_json       else []
    verdicts = json.loads(s.recruiter_verdicts_json) if s.recruiter_verdicts_json else []

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
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif !important; }
    .stApp { background: #F0F4F8 !important; }
    #MainMenu, footer, header { visibility: hidden; }

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
        finally:
            _db.close()

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

        if st.session_state.get("org_id"):
            from saas.saas_auth import show_saas_billing_sidebar
            show_saas_billing_sidebar(st.session_state.org_id)

        st.markdown("---")
        if st.button("🚪 Log out", use_container_width=True, key="sidebar_logout"):
            _recruiter_logout()

    # ── TOP BAR (full width) ──
    st.markdown("""
    <div class="ps-topbar">
        <h2>🏢 PsySense — Recruiter Intelligence Dashboard</h2>
        <p>AI-powered interview analysis platform</p>
    </div>
    """, unsafe_allow_html=True)

    _org = st.session_state.get("org_id")
    if st.session_state.get("show_billing_page") and not _org:
        st.session_state.show_billing_page = False
    if st.session_state.get("show_billing_page") and _org:
        b1, b2 = st.columns([1, 4])
        with b1:
            if st.button("← Back to dashboard", key="billing_back"):
                st.session_state.show_billing_page = False
                st.rerun()
        with b2:
            st.caption("Manage your subscription and usage.")
        from saas.saas_billing import show_billing_page
        show_billing_page(_org)
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

    st.markdown(f"**{len(filtered)} candidate(s)**")

    STATUS_ICON = {"Pending": "🕐", "Shortlisted": "⭐", "Rejected": "❌"}
    BADGE_CLASS = {"Strong Advance": "vb-green", "Advance": "vb-blue",
                   "Borderline": "vb-yellow",    "Do Not Advance": "vb-red"}

    for s in filtered:
        sc      = s.final_score or 0
        emoji   = "🟢" if sc >= 75 else ("🟡" if sc >= 55 else "🔴")
        verdict = _verdict_from_score(s.cognitive_score or 5.0)
        bc      = BADGE_CLASS.get(verdict, "vb-yellow")
        si      = STATUS_ICON.get(s.status, "")
        insight_data = json.loads(s.insight_json) if s.insight_json else {}

        with st.container(border=True):
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2.5, 0.8, 0.7, 0.7, 0.7, 1.2, 1.0])
            c1.markdown(
                f"**{s.candidate_name}**  \n`{s.username or '—'}` · {si} {s.status}")
            c2.markdown(f"{emoji} **{sc}**")
            c3.caption(f"🧠 {round(s.cognitive_score or 0, 1)}")
            c4.caption(f"😊 {round(s.emotion_score or 0, 1)}")
            c5.caption(f"👁 {round(s.engagement_score or 0, 1)}")
            c6.markdown(
                f'<span class="vbadge {bc}">{_verdict_badge(verdict)}</span>',
                unsafe_allow_html=True)
            c7.caption(s.created_at.strftime("%d %b %Y"))

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

    insight  = json.loads(s.insight_json)           if s.insight_json           else {}
    per_q    = json.loads(s.per_question_json)       if s.per_question_json       else []
    verdicts = json.loads(s.recruiter_verdicts_json) if s.recruiter_verdicts_json else []

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
                "Status", ["Pending", "Shortlisted", "Rejected"],
                index=["Pending", "Shortlisted", "Rejected"].index(
                    s.status or "Pending"),
                key=f"status_{session_id}")
            if st.button("Update Status", key=f"upd_{session_id}",
                         use_container_width=True):
                update_candidate_status(session_id, new_status)
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