"""
recruiter_dashboard.py (Enhanced)
---------------------------------
Recruiter-only view with:
- Top-tier dashboard design with premium aesthetics
- Prominent logout button in header
- PDF download for all candidates
- Integrated recruiter insights from insight_engine
- Better filtering, sorting, and UI/UX
- Advanced analytics

Run with:
    streamlit run app.py
    (when role == "recruiter")
"""

import io
import json
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

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

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION & THEMING
# ═══════════════════════════════════════════════════════════════════════════

# Premium color palette
COLORS = {
    "primary":      "#1D9E75",      # Forest green
    "secondary":    "#185FA5",      # Deep blue
    "accent":       "#E8A020",      # Gold/amber
    "danger":       "#CC2222",      # Red
    "success":      "#1D9E75",      # Green
    "info":         "#4C9ED9",      # Light blue
    "background":   "#F8FAFB",      # Off-white
    "surface":      "#FFFFFF",      # White
    "border":       "#E0E4E8",      # Light gray
    "text_dark":    "#1A1F36",      # Dark text
    "text_light":   "#6B7280",      # Light text
}

EMOTION_EMOJI = {
    "happy": "😊", "neutral": "😐", "sad": "😢",
    "angry": "😠", "fear": "😰", "surprise": "😲", "disgust": "😑"
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _score_emoji(s: float) -> str:
    if s >= 8:  return "🟢"
    if s >= 6:  return "🟡"
    if s >= 4:  return "🟠"
    return "🔴"


def _score_label(s: float) -> str:
    if s >= 8:  return "Excellent"
    if s >= 6:  return "Good"
    if s >= 4:  return "Average"
    return "Needs Work"


def _verdict_badge(v: str) -> str:
    badges = {
        "Strong Advance": "🟢 Strong Advance",
        "Advance":        "🔵 Advance",
        "Borderline":     "🟡 Borderline",
        "Do Not Advance": "🔴 Do Not Advance",
    }
    return badges.get(v, v or "—")


def _get_verdict_from_score(avg_cog: float) -> str:
    """Compute recruiter verdict based on cognitive score."""
    if avg_cog >= 7.5:  return "Strong Advance"
    if avg_cog >= 5.5:  return "Advance"
    if avg_cog >= 3.5:  return "Borderline"
    return "Do Not Advance"


def _get_verdict_color(verdict: str) -> str:
    """Return hex color for verdict badge."""
    color_map = {
        "Strong Advance": COLORS["success"],
        "Advance":        COLORS["secondary"],
        "Borderline":     COLORS["accent"],
        "Do Not Advance": COLORS["danger"],
    }
    return color_map.get(verdict, COLORS["text_light"])


# ═══════════════════════════════════════════════════════════════════════════
# PDF GENERATOR (Enhanced)
# ═══════════════════════════════════════════════════════════════════════════

def generate_candidate_pdf(session_id: int) -> bytes:
    """
    Build and return a professional PDF report for one candidate session.
    Uses reportlab Platypus for clean multi-page layout.
    Includes recruiter insights, verdicts, and detailed analytics.
    """
    s = get_session_by_id(session_id)
    if not s:
        return b""

    insight  = json.loads(s.insight_json) if s.insight_json else {}
    per_q    = json.loads(s.per_question_json) if s.per_question_json else []
    verdicts = json.loads(s.recruiter_verdicts_json) if s.recruiter_verdicts_json else []

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm,
        title=f"PsySense Report — {s.candidate_name}",
    )

    styles = getSampleStyleSheet()

    # ── Custom Styles ─────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor(COLORS["primary"]),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    h1_style = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=14, textColor=colors.HexColor(COLORS["secondary"]),
        spaceAfter=6, fontName="Helvetica-Bold",
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=11, textColor=colors.HexColor(COLORS["text_dark"]),
        spaceAfter=4, fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, leading=13, spaceAfter=3,
    )
    caption_style = ParagraphStyle(
        "Caption", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor(COLORS["text_light"]),
        spaceAfter=2,
    )
    answer_style = ParagraphStyle(
        "Answer", parent=styles["Normal"],
        fontSize=9, leading=13,
        backColor=colors.HexColor("#F0F4F8"),
        borderPad=5, spaceAfter=4,
    )

    def hr():
        return HRFlowable(width="100%", thickness=0.5,
                         color=colors.HexColor(COLORS["border"]),
                         spaceAfter=8)

    def sp(h=6):
        return Spacer(1, h)

    # ── Compute verdict ────────────────────────────────────────────────
    avg_cog = s.cognitive_score or 5.0
    overall_verdict = _get_verdict_from_score(avg_cog)
    verdict_color = _get_verdict_color(overall_verdict)
    sc = s.final_score or 0

    # ── Build story ────────────────────────────────────────────────────
    story = []

    # Header
    story.append(Paragraph("PsySense AI Interview Platform", caption_style))
    story.append(Paragraph(f"Candidate Report: {s.candidate_name}", title_style))
    story.append(sp(2))

    meta_text = (
        f"Date: {s.created_at.strftime('%d %b %Y, %H:%M')}  |  "
        f"Questions: {s.questions_answered}  |  "
        f"{'JD-Scored ✓' if s.jd_used else 'No JD'}  |  "
        f"Session #{s.id}"
    )
    story.append(Paragraph(meta_text, caption_style))
    story.append(sp(6))
    story.append(hr())

    # Verdict banner
    story.append(Paragraph(
        f'<font color="{verdict_color}"><b>Recruiter Verdict: {overall_verdict}</b></font> — '
        f'Overall Score: <b>{sc}/100</b>  |  '
        f'Recommendation: <b>{insight.get("recommendation", "N/A")}</b>',
        body_style,
    ))
    story.append(sp(8))

    # Score Summary Table
    story.append(Paragraph("Score Summary", h1_style))
    score_data = [
        ["Dimension", "Score", "Level"],
        ["Answer Quality (Cognitive)", f"{round(s.cognitive_score or 5, 1)} / 10",
         _score_label(s.cognitive_score or 5)],
        ["Emotional Tone (Speech)", f"{round(s.emotion_score or 5, 1)} / 10",
         _score_label(s.emotion_score or 5)],
        ["Attentiveness (Engagement)", f"{round(s.engagement_score or 5, 1)} / 10",
         _score_label(s.engagement_score or 5)],
        ["Overall Behavioural Score", f"{sc} / 100", ""],
    ]

    score_table = Table(score_data, colWidths=[90*mm, 40*mm, 40*mm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(COLORS["secondary"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#F7F9FC"), colors.white]),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(COLORS["border"])),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
    ]))
    story.append(score_table)
    story.append(sp(10))

    # AI Recruiter Assessment (Insight) — RECRUITER ONLY
    if insight:
        story.append(hr())
        story.append(Paragraph("🎯 AI Recruiter Assessment", h1_style))

        if insight.get("strengths"):
            story.append(Paragraph("Strengths", h2_style))
            for item in insight["strengths"]:
                story.append(Paragraph(f"✓ {item}", body_style))
            story.append(sp(4))

        if insight.get("weaknesses"):
            story.append(Paragraph("Areas to Improve", h2_style))
            for item in insight["weaknesses"]:
                story.append(Paragraph(f"⚠ {item}", body_style))
            story.append(sp(4))

        if insight.get("recommendation"):
            story.append(Paragraph(
                f"<b>Hiring Recommendation:</b> {insight['recommendation']}", body_style
            ))
        story.append(sp(10))

    # Per-Question Breakdown
    if per_q:
        story.append(hr())
        story.append(Paragraph("Question-by-Question Breakdown", h1_style))
        story.append(sp(4))

        DIM_LABELS = {
            "clarity": "Clarity", "relevance": "Relevance",
            "star_quality": "STAR", "specificity": "Specificity",
            "communication": "Communication", "job_fit": "Job Fit",
        }

        for i, qd in enumerate(per_q):
            v_label = qd.get("verdict", verdicts[i] if i < len(verdicts) else "")

            story.append(Paragraph(f"<b>Q{i+1}:</b> {qd.get('question', '')}", h2_style))

            if v_label:
                story.append(Paragraph(f"Verdict: <b>{v_label}</b>", caption_style))

            ans_text = qd.get("answer") or "No answer recorded."
            story.append(Paragraph(ans_text, answer_style))

            # Scores mini-table
            q_scores = [
                ["Answer Quality", "Emotional Tone", "Attentiveness", "Face Visible"],
                [
                    f"{round(qd.get('cognitive', 5), 1)}/10",
                    f"{round(qd.get('emotion', 5), 1)}/10",
                    f"{round(qd.get('engagement', 5), 1)}/10",
                    f"{100 - qd.get('absence', 0)*100:.0f}%",
                ],
            ]
            q_tbl = Table(q_scores, colWidths=[42*mm, 42*mm, 42*mm, 42*mm])
            q_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(COLORS["info"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(COLORS["border"])),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(q_tbl)
            story.append(sp(6))

            story.append(hr())

    # Footer
    story.append(sp(8))
    story.append(Paragraph(
        "This report was generated by PsySense AI Interview Platform. "
        "For internal recruiter use only. Confidential.",
        caption_style,
    ))

    doc.build(story)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def show_recruiter_dashboard():
    """
    Premium recruiter dashboard with top-tier design.
    Features: logout button, PDF downloads, insights, advanced analytics.
    """
    
    # ── Page Config ────────────────────────────────────────────────────
    st.set_page_config(
        page_title="PsySense Recruiter Dashboard",
        page_icon="🏢",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Custom CSS for Premium Design ──────────────────────────────────
    st.markdown(f"""
    <style>
    :root {{
        --color-primary: {COLORS['primary']};
        --color-secondary: {COLORS['secondary']};
        --color-accent: {COLORS['accent']};
        --color-danger: {COLORS['danger']};
        --color-background: {COLORS['background']};
        --color-surface: {COLORS['surface']};
        --color-border: {COLORS['border']};
        --color-text-dark: {COLORS['text_dark']};
        --color-text-light: {COLORS['text_light']};
    }}

    /* Enhanced header styling */
    header {{
        background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['secondary']} 100%);
        padding: 20px 0 !important;
    }}

    /* Premium card styling */
    .recruiter-card {{
        border: 1px solid {COLORS['border']};
        border-radius: 12px;
        padding: 20px;
        background: {COLORS['surface']};
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        transition: all 0.3s ease;
    }}

    .recruiter-card:hover {{
        box-shadow: 0 8px 24px rgba(0,0,0,0.12);
        transform: translateY(-2px);
    }}

    /* Metric cards */
    .metric-card {{
        background: linear-gradient(135deg, {COLORS['primary']}0a 0%, {COLORS['secondary']}0a 100%);
        border-left: 4px solid {COLORS['primary']};
        padding: 16px;
        border-radius: 8px;
        margin: 8px 0;
    }}

    /* Verdict badges */
    .verdict-strong {{
        background-color: {COLORS['success']}1a;
        color: {COLORS['success']};
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }}

    .verdict-advance {{
        background-color: {COLORS['secondary']}1a;
        color: {COLORS['secondary']};
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }}

    .verdict-borderline {{
        background-color: {COLORS['accent']}1a;
        color: {COLORS['accent']};
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }}

    .verdict-danger {{
        background-color: {COLORS['danger']}1a;
        color: {COLORS['danger']};
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }}

    /* Button enhancements */
    button {{
        border-radius: 8px;
        transition: all 0.2s ease;
    }}

    button:hover {{
        transform: scale(1.02);
    }}

    /* Logout button styling */
    .logout-btn {{
        background-color: {COLORS['danger']} !important;
        color: white !important;
        border-radius: 8px;
        font-weight: 600;
        padding: 8px 16px;
    }}

    .logout-btn:hover {{
        background-color: #a01a1a !important;
    }}

    /* Make all text black */
    body, p, h1, h2, h3, h4, h5, h6, span, div, button, input, textarea {{
        color: {COLORS['text_dark']} !important;
    }}

    /* Override Streamlit defaults to ensure visibility */
    .stMarkdown {{
        color: {COLORS['text_dark']} !important;
    }}

    .stMetric {{
        color: {COLORS['text_dark']} !important;
    }}

    .stButton > button {{
        color: {COLORS['text_dark']} !important;
    }}

    /* Table styling */
    table {{
        border-collapse: collapse;
        width: 100%;
        color: {COLORS['text_dark']} !important;
    }}

    thead {{
        background-color: {COLORS['secondary']};
        color: white !important;
    }}

    tbody {{
        color: {COLORS['text_dark']} !important;
    }}

    tbody tr:nth-child(even) {{
        background-color: {COLORS['background']};
        color: {COLORS['text_dark']} !important;
    }}

    tbody tr:hover {{
        background-color: {COLORS['primary']}0f;
        color: {COLORS['text_dark']} !important;
    }}

    /* Make labels and captions black */
    .stCaption {{
        color: {COLORS['text_dark']} !important;
    }}

    .stSelectbox label {{
        color: {COLORS['text_dark']} !important;
    }}

    .stTextInput label {{
        color: {COLORS['text_dark']} !important;
    }}

    .stTextArea label {{
        color: {COLORS['text_dark']} !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    # ── Header with Logo & Logout ──────────────────────────────────────
    header_col1, header_col2, header_col3 = st.columns([2, 3, 1])
    
    with header_col1:
        st.markdown(f"### 🏢 PsySense")
        st.caption("Recruiter Dashboard")
    
    with header_col2:
        st.markdown("")  # spacer
    
    with header_col3:
        st.markdown("")  # spacer
        if st.button(
            "🚪 Logout",
            key="recruiter_logout_btn",
            use_container_width=True,
            help="Sign out of your recruiter account"
        ):
            st.session_state.clear()
            st.rerun()

    st.markdown("---")

    # ── Sidebar Navigation ─────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 📊 Navigation")
        
        nav_mode = st.radio(
            "View",
            ["📋 Candidates", "👥 Students", "📈 Analytics"],
            label_visibility="collapsed"
        )

        st.markdown("---")
        st.markdown("### ⚙️ Quick Actions")
        
        if st.session_state.get("recruiter_detail_id"):
            if st.button("← Back to List", use_container_width=True):
                st.session_state.recruiter_detail_id = None
                st.rerun()

        st.markdown("---")
        st.caption("💡 Tip: Click 'Full Report' to see detailed analytics and insights.")

    # ── Route to Views ─────────────────────────────────────────────────
    if st.session_state.get("recruiter_detail_id"):
        _show_candidate_detail(st.session_state.recruiter_detail_id)
    elif nav_mode == "👥 Students":
        _show_registered_students()
    elif nav_mode == "📈 Analytics":
        _show_analytics()
    else:
        _show_overview()


# ═══════════════════════════════════════════════════════════════════════════
# OVERVIEW VIEW
# ═══════════════════════════════════════════════════════════════════════════

def _show_overview():
    """Display candidate overview with filters, search, and insights."""
    
    sessions = get_all_sessions()

    if not sessions:
        st.info(
            "🎤 No interviews yet. Candidates will appear here automatically "
            "after completing their interview."
        )
        return

    # ── Key Metrics ────────────────────────────────────────────────────
    total = len(sessions)
    avg_s = round(sum(s.final_score or 0 for s in sessions) / total, 1)
    passed = sum(1 for s in sessions if (s.final_score or 0) >= 55)
    flagged = sum(1 for s in sessions if s.flagged)
    shortlisted = sum(1 for s in sessions if s.status == "Shortlisted")

    metric_cols = st.columns(5)
    with metric_cols[0]:
        st.metric("👥 Total Candidates", total)
    with metric_cols[1]:
        st.metric("📊 Avg Score", f"{avg_s}/100")
    with metric_cols[2]:
        st.metric("✅ Pass Rate", f"{round(passed / total * 100, 1)}%")
    with metric_cols[3]:
        st.metric("🚩 Flagged", flagged)
    with metric_cols[4]:
        st.metric("⭐ Shortlisted", shortlisted)

    st.markdown("---")

    # ── Filters & Search ───────────────────────────────────────────────
    col_search, col_status, col_sort = st.columns([3, 2, 2])
    
    with col_search:
        search = st.text_input(
            "🔍 Search by name",
            placeholder="Type candidate name...",
            label_visibility="collapsed"
        )
    
    with col_status:
        status_filter = st.selectbox(
            "Status Filter",
            ["All", "Pending", "Shortlisted", "Rejected"],
            label_visibility="collapsed"
        )
    
    with col_sort:
        sort_by = st.selectbox(
            "Sort By",
            ["Date ↓", "Score ↓", "Score ↑", "Name A-Z"],
            label_visibility="collapsed"
        )

    # ── Apply Filters ──────────────────────────────────────────────────
    filtered = list(sessions)
    
    if search.strip():
        filtered = [s for s in filtered 
                   if search.lower() in s.candidate_name.lower()]
    
    if status_filter != "All":
        filtered = [s for s in filtered if s.status == status_filter]

    sort_key = {
        "Score ↓": lambda s: -(s.final_score or 0),
        "Score ↑": lambda s: (s.final_score or 0),
        "Name A-Z": lambda s: s.candidate_name.lower(),
    }.get(sort_by)
    
    if sort_key:
        filtered.sort(key=sort_key)

    st.markdown(f"**{len(filtered)} candidate(s) shown**")

    # ── Candidate List ─────────────────────────────────────────────────
    STATUS_ICON = {"Pending": "🕐", "Shortlisted": "⭐", "Rejected": "❌"}

    for s in filtered:
        sc = s.final_score or 0
        emoji = "🟢" if sc >= 75 else ("🟡" if sc >= 55 else "🔴")
        si = STATUS_ICON.get(s.status, "")
        
        insight_data = json.loads(s.insight_json) if s.insight_json else {}
        avg_cog = s.cognitive_score or 5.0
        verdict = _get_verdict_from_score(avg_cog)

        with st.container(border=True):
            # Row 1: Name, scores, verdict
            row1_cols = st.columns([2.5, 0.8, 0.7, 0.7, 0.7, 1.0, 1.2])
            
            row1_cols[0].markdown(
                f"**{s.candidate_name}**  \n"
                f"`{s.username or '—'}` · {si} {s.status}"
            )
            row1_cols[1].markdown(f"{emoji} **{sc}**")
            row1_cols[2].caption(f"🧠 {s.cognitive_score or '—'}")
            row1_cols[3].caption(f"😊 {s.emotion_score or '—'}")
            row1_cols[4].caption(f"👁 {s.engagement_score or '—'}")
            
            # Verdict badge
            verdict_color = _get_verdict_color(verdict)
            row1_cols[5].markdown(
                f'<span class="verdict-{verdict.lower().replace(" ", "-")}">'
                f'{_verdict_badge(verdict)}</span>',
                unsafe_allow_html=True
            )
            
            row1_cols[6].caption(s.created_at.strftime("%d %b %Y"))

            # Row 2: Action buttons
            btn_cols = st.columns([1.5, 1, 1])
            
            with btn_cols[0]:
                if st.button("📄 Full Report", key=f"view_{s.id}"):
                    st.session_state.recruiter_detail_id = s.id
                    st.rerun()

            with btn_cols[1]:
                pdf_bytes = generate_candidate_pdf(s.id)
                st.download_button(
                    label="⬇ Download PDF",
                    data=pdf_bytes,
                    file_name=f"psysense_{s.candidate_name.replace(' ', '_')}_{s.id}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{s.id}",
                    use_container_width=True,
                )

            with btn_cols[2]:
                if st.button("⭐ Flag", key=f"flag_{s.id}"):
                    st.info("Flagged for review")

            # Row 3: AI Insight
            if insight_data.get("recommendation") or insight_data.get("strengths"):
                with st.expander("🎯 AI Insight", expanded=False):
                    rec = insight_data.get("recommendation", "N/A")
                    if rec and rec != "N/A":
                        st.info(f"**Recommendation:** {rec}")

                    col_s, col_w = st.columns(2)
                    
                    with col_s:
                        strengths = insight_data.get("strengths", [])
                        if strengths:
                            st.markdown("**✅ Strengths**")
                            for item in strengths:
                                st.caption(f"→ {item}")

                    with col_w:
                        weaknesses = insight_data.get("weaknesses", [])
                        if weaknesses:
                            st.markdown("**⚠️ Areas to Improve**")
                            for item in weaknesses:
                                st.caption(f"→ {item}")

    # ── Score Distribution Chart ───────────────────────────────────────
    if total >= 3:
        st.markdown("---")
        st.markdown("### 📊 Score Distribution")
        
        score_vals = [s.final_score or 0 for s in sessions]
        buckets = [
            ("Needs Work\n(<35)", sum(1 for v in score_vals if v < 35)),
            ("Average\n(35–55)", sum(1 for v in score_vals if 35 <= v < 55)),
            ("Good\n(55–75)", sum(1 for v in score_vals if 55 <= v < 75)),
            ("Strong\n(75+)", sum(1 for v in score_vals if v >= 75)),
        ]
        
        fig = go.Figure(go.Bar(
            x=[b[0] for b in buckets],
            y=[b[1] for b in buckets],
            marker_color=[COLORS["danger"], COLORS["accent"], 
                         COLORS["info"], COLORS["success"]],
            text=[b[1] for b in buckets],
            textposition="outside",
        ))
        
        fig.update_layout(
            yaxis_title="Candidates",
            xaxis_title="Performance Level",
            showlegend=False,
            height=320,
            margin=dict(t=20, b=80),
        )
        
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# CANDIDATE DETAIL VIEW
# ═══════════════════════════════════════════════════════════════════════════

def _show_candidate_detail(session_id: int):
    """Display detailed candidate report with insights and analytics."""
    
    s = get_session_by_id(session_id)
    if not s:
        st.error("❌ Candidate record not found.")
        return

    insight = json.loads(s.insight_json) if s.insight_json else {}
    per_q = json.loads(s.per_question_json) if s.per_question_json else []
    verdicts = json.loads(s.recruiter_verdicts_json) if s.recruiter_verdicts_json else []

    sc = s.final_score or 0
    avg_cog = s.cognitive_score or 5.0
    overall_verdict = _get_verdict_from_score(avg_cog)

    # ── Header with PDF Download ───────────────────────────────────────
    h_col1, h_col2 = st.columns([4, 1])
    
    with h_col1:
        st.markdown(f"## 📋 {s.candidate_name}")
        meta_text = (
            f"📅 {s.created_at.strftime('%d %b %Y, %H:%M')} · "
            f"🎤 {s.questions_answered} questions · "
            f"{'JD-scored ✓' if s.jd_used else 'No JD'} · "
            f"ID #{s.id}"
        )
        st.caption(meta_text)

    with h_col2:
        st.markdown("")
        pdf_bytes = generate_candidate_pdf(session_id)
        st.download_button(
            label="⬇ Download PDF",
            data=pdf_bytes,
            file_name=f"psysense_{s.candidate_name.replace(' ', '_')}_{s.id}.pdf",
            mime="application/pdf",
            key=f"pdf_detail_{session_id}",
            use_container_width=True,
        )

    st.markdown("---")

    # ── Verdict Banner ─────────────────────────────────────────────────
    verdict_color = _get_verdict_color(overall_verdict)
    st.markdown(f"""
    <div style="
        background: {verdict_color}15;
        border-left: 4px solid {verdict_color};
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 20px;
    ">
        <h3 style="margin: 0; color: {verdict_color};">
            {_verdict_badge(overall_verdict)}
        </h3>
        <p style="margin: 8px 0 0 0; color: #666;">
            Score: <b>{sc}/100</b> | 
            Recommendation: <b>{insight.get("recommendation", "N/A")}</b>
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Score Gauge ────────────────────────────────────────────────────
    col_gauge, col_breakdown = st.columns([1, 1])
    
    with col_gauge:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=sc,
            title={"text": "Overall Score"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": verdict_color},
                "steps": [
                    {"range": [0, 35], "color": f"{COLORS['danger']}20"},
                    {"range": [35, 55], "color": f"{COLORS['accent']}20"},
                    {"range": [55, 75], "color": f"{COLORS['info']}20"},
                    {"range": [75, 100], "color": f"{COLORS['success']}20"},
                ],
            },
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col_breakdown:
        fig_bar = go.Figure(go.Bar(
            x=["Answer Quality", "Emotional Tone", "Attentiveness"],
            y=[s.cognitive_score or 5, s.emotion_score or 5, s.engagement_score or 5],
            marker_color=[COLORS["info"], COLORS["accent"], COLORS["success"]],
            text=[
                f"{s.cognitive_score}  {_score_emoji(s.cognitive_score or 0)}",
                f"{s.emotion_score}  {_score_emoji(s.emotion_score or 0)}",
                f"{s.engagement_score}  {_score_emoji(s.engagement_score or 0)}",
            ],
            textposition="outside",
        ))
        fig_bar.update_layout(
            title="Signal Breakdown (out of 10)",
            yaxis=dict(range=[0, 12]),
            showlegend=False,
            height=300,
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # ── Recruiter Actions ──────────────────────────────────────────────
    with st.expander("⚙️ Recruiter Actions", expanded=True):
        act_col1, act_col2 = st.columns([1, 2])
        
        with act_col1:
            new_status = st.selectbox(
                "Candidate Status",
                ["Pending", "Shortlisted", "Rejected"],
                index=["Pending", "Shortlisted", "Rejected"].index(s.status or "Pending"),
                key=f"status_{session_id}",
            )
            if st.button("Update Status", key=f"update_{session_id}", use_container_width=True):
                update_candidate_status(session_id, new_status)
                st.success(f"✅ Status updated to {new_status}")
                st.rerun()

        with act_col2:
            notes = st.text_area(
                "Recruiter Notes",
                value=s.recruiter_notes or "",
                placeholder="Add private notes about this candidate...",
                key=f"notes_{session_id}",
                height=80,
            )
            if st.button("💾 Save Notes", key=f"save_notes_{session_id}", use_container_width=True):
                save_recruiter_notes(session_id, notes)
                st.success("✅ Notes saved")

    st.markdown("---")

    # ── AI Assessment (RECRUITER ONLY) ─────────────────────────────────
    if insight:
        st.markdown("### 🎯 AI Recruiter Assessment")
        
        ins_col1, ins_col2 = st.columns(2)
        
        with ins_col1:
            strengths = insight.get("strengths", [])
            if strengths:
                st.markdown("**✅ Strengths**")
                for item in strengths:
                    st.success(f"→ {item}")

        with ins_col2:
            weaknesses = insight.get("weaknesses", [])
            if weaknesses:
                st.markdown("**⚠️ Areas to Improve**")
                for item in weaknesses:
                    st.warning(f"→ {item}")

        if insight.get("recommendation"):
            st.info(f"**Hiring Recommendation:** {insight['recommendation']}")

        st.markdown("---")

    # ── Score Trend ────────────────────────────────────────────────────
    if per_q:
        st.markdown("### 📈 Score Trend Across Questions")
        
        qlabels = [f"Q{i+1}" for i in range(len(per_q))]
        traces = [
            ("Answer Quality", [q.get("cognitive", 5) for q in per_q], COLORS["info"]),
            ("Emotional Tone", [q.get("emotion", 5) for q in per_q], COLORS["accent"]),
            ("Attentiveness", [q.get("engagement", 5) for q in per_q], COLORS["success"]),
        ]
        
        fig_trend = go.Figure()
        for name, vals, color in traces:
            fig_trend.add_trace(go.Scatter(
                x=qlabels, y=vals, mode="lines+markers", name=name,
                line=dict(color=color, width=2.5),
                marker=dict(size=8),
            ))
        
        fig_trend.update_layout(
            yaxis=dict(range=[0, 10], title="Score (out of 10)"),
            xaxis_title="Question",
            legend=dict(orientation="h", y=-0.2),
            hovermode="x unified",
            height=300,
            margin=dict(b=80),
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown("---")

    # ── Per-Question Breakdown ─────────────────────────────────────────
    if per_q:
        st.markdown("### Question-by-Question Breakdown")

        DIM_LABELS = {
            "clarity": "Clarity",
            "relevance": "Relevance",
            "star_quality": "STAR Quality",
            "specificity": "Specificity",
            "communication": "Communication",
            "job_fit": "Job Fit",
        }

        for i, qd in enumerate(per_q):
            v_label = qd.get("verdict", verdicts[i] if i < len(verdicts) else "")
            badge = _verdict_badge(v_label)

            with st.expander(f"Q{i+1}: {qd.get('question', '')}  {badge}"):
                st.markdown("**Candidate Answer:**")
                st.info(qd.get("answer") or "_No answer recorded._")

                # Metrics
                m_cols = st.columns(4)
                m_cols[0].metric("Answer Quality", f"{round(qd.get('cognitive', 5), 1)}/10")
                m_cols[1].metric("Emotional Tone", f"{round(qd.get('emotion', 5), 1)}/10")
                m_cols[2].metric("Attentiveness", f"{round(qd.get('engagement', 5), 1)}/10")
                m_cols[3].metric("Face Visible", f"{100 - qd.get('absence', 0) * 100:.0f}%")

                # Dimensions
                dims = qd.get("dimensions", {})
                if dims:
                    st.markdown("**📊 Dimension Scores**")
                    d_cols = st.columns(3)
                    d_items = [(k, v) for k, v in dims.items()
                              if k in DIM_LABELS and isinstance(v, (int, float))]
                    for j, (dim, val) in enumerate(d_items):
                        d_cols[j % 3].metric(DIM_LABELS[dim], f"{val}/10")

                    if dims.get("summary"):
                        st.caption(f"💬 {dims['summary']}")
                    
                    k_col, i_col = st.columns(2)
                    if dims.get("key_strength"):
                        k_col.success(f"✅ {dims['key_strength']}")
                    if dims.get("key_improvement"):
                        i_col.warning(f"⚠️ {dims['key_improvement']}")

                # Speech
                sb = qd.get("speech", {})
                if sb:
                    st.markdown("**🎙️ Speech Quality**")
                    sb_cols = st.columns(3)
                    sb_cols[0].metric("Emotion", f"{sb.get('emotion_model', 5)}/10")
                    sb_cols[1].metric("Fluency", f"{sb.get('fluency_score', 5)}/10")
                    sb_cols[2].metric("Voice Energy", f"{sb.get('voice_score', 5)}/10")
                    
                    if sb.get("dominant_emotion"):
                        st.caption(f"Dominant: **{sb['dominant_emotion'].capitalize()}**")

                # Facial emotion
                fe = qd.get("facial_emotion", {})
                if fe and fe.get("breakdown"):
                    dominant = fe.get("dominant", "neutral")
                    label_map = {
                        "happy": "Confident", "neutral": "Composed",
                        "surprise": "Off guard", "fear": "Nervous",
                        "sad": "Low energy", "angry": "Stressed",
                        "disgust": "Uncomfortable",
                    }
                    emoji = EMOTION_EMOJI.get(dominant, "😐")
                    st.markdown(f"**😶 Facial Emotion:** {emoji} {label_map.get(dominant, dominant.capitalize())}")


# ═══════════════════════════════════════════════════════════════════════════
# REGISTERED STUDENTS VIEW
# ═══════════════════════════════════════════════════════════════════════════

def _show_registered_students():
    """Display registered student accounts and interview counts."""
    
    st.markdown("### 👥 Registered Students")
    
    users = get_all_users()
    if not users:
        st.info("No student accounts registered yet.")
        return

    sessions = get_all_sessions()
    session_count = {}
    for s in sessions:
        if s.username:
            session_count[s.username] = session_count.get(s.username, 0) + 1

    for u in users:
        count = session_count.get(u.username, 0)
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.markdown(f"**{u.display_name or u.username}**  \n`{u.username}`")
            col2.metric("Interviews", count)
            col3.caption(u.created_at.strftime("%d %b %Y"))


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS VIEW
# ═══════════════════════════════════════════════════════════════════════════

def _show_analytics():
    """Display advanced analytics dashboard."""
    
    st.markdown("### 📈 Advanced Analytics")
    
    sessions = get_all_sessions()
    
    if not sessions:
        st.info("No data available for analytics yet.")
        return

    # Performance distribution
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Cognitive Score Distribution")
        cog_scores = [s.cognitive_score or 5 for s in sessions]
        fig_cog = go.Figure(go.Histogram(
            x=cog_scores, nbinsx=8,
            marker_color=COLORS["info"],
            name="Cognitive Scores",
        ))
        fig_cog.update_layout(
            xaxis_title="Score (out of 10)",
            yaxis_title="Candidates",
            height=300,
            showlegend=False,
        )
        st.plotly_chart(fig_cog, use_container_width=True)

    with col2:
        st.markdown("#### Overall Score Distribution")
        final_scores = [s.final_score or 0 for s in sessions]
        fig_final = go.Figure(go.Histogram(
            x=final_scores, nbinsx=10,
            marker_color=COLORS["success"],
            name="Final Scores",
        ))
        fig_final.update_layout(
            xaxis_title="Score (out of 100)",
            yaxis_title="Candidates",
            height=300,
            showlegend=False,
        )
        st.plotly_chart(fig_final, use_container_width=True)

    # Signal comparison
    st.markdown("---")
    st.markdown("#### Signal Comparison")
    
    signals = {
        "Answer Quality": sum(s.cognitive_score or 0 for s in sessions) / len(sessions),
        "Emotional Tone": sum(s.emotion_score or 0 for s in sessions) / len(sessions),
        "Attentiveness": sum(s.engagement_score or 0 for s in sessions) / len(sessions),
    }
    
    fig_signals = go.Figure(go.Bar(
        x=list(signals.keys()),
        y=list(signals.values()),
        marker_color=[COLORS["info"], COLORS["accent"], COLORS["success"]],
        text=[f"{v:.1f}/10" for v in signals.values()],
        textposition="outside",
    ))
    fig_signals.update_layout(
        yaxis=dict(range=[0, 10]),
        yaxis_title="Average Score",
        showlegend=False,
        height=300,
    )
    st.plotly_chart(fig_signals, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    show_recruiter_dashboard()