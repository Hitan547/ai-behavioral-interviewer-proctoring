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
    get_session_by_id, get_session_by_id_for_org, get_sessions_by_org,
    update_candidate_status, save_recruiter_notes,
    get_job_postings_by_org,
    get_jd_stats,
    get_candidates_by_jd,
    check_expired_invites,
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


def _current_org_id():
    return st.session_state.get("org_id")


def _decision_for_session(s):
    score = s.final_score or 0
    verdict = _verdict_from_score(s.cognitive_score or 5.0)
    risk = getattr(s, "proctoring_risk", "Low") or "Low"
    if verdict in ("Strong Advance", "Advance") and score >= 55 and risk in ("Low", "Medium"):
        return "Advance", "vb-green"
    if verdict == "Do Not Advance" or score < 45 or risk in ("High", "Critical"):
        return "Reject", "vb-red"
    return "Hold", "vb-yellow"


def _invitation_bucket(status: str) -> str:
    status = status or "Shortlisted"
    if status == "Expired":
        return "Expired"
    if status == "In Progress":
        return "Started"
    if status in ("Completed", "Passed", "Below Threshold"):
        return "Completed"
    if status in ("Invited", "Shortlisted"):
        return "Invited"
    return status


def _invitation_badge_class(bucket: str) -> str:
    return {
        "Invited": "vb-blue",
        "Started": "vb-yellow",
        "Completed": "vb-green",
        "Expired": "vb-red",
    }.get(bucket, "vb-yellow")


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────
def generate_candidate_pdf(session_id: int, org_id: str = None) -> bytes:
    s = get_session_by_id_for_org(session_id, org_id) if org_id else get_session_by_id(session_id)
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
         ["Delivery Signal", f"{round(s.emotion_score or 5,1)}/10",
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
                [["Answer Quality", "Delivery Signal", "Attentiveness", "Face Visible"],
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

    # ── Proctoring / Anti-Cheating section ──
    proctor = _safe_json_loads(getattr(s, 'proctoring_json', None), {})
    if proctor:
        story += [hr(), Paragraph("Anti-Cheating Proctoring", h1_s)]
        risk = proctor.get("risk_level", "Low")
        risk_color = {"Low": C["primary"], "Medium": C["accent"], "High": C["danger"]}.get(risk, C["muted"])
        story.append(Paragraph(
            f'<font color="{risk_color}"><b>Risk Level: {risk}</b></font>', body_s))
        # Summary stats
        pt = Table(
            [["Tab Switches", "Paste Attempts", "Fullscreen Exits", "Multi-Face", "Screens"],
             [str(proctor.get("tab_switch_count", 0)),
              str(proctor.get("paste_attempt_count", 0)),
              str(proctor.get("fullscreen_exit_count", 0)),
              str(proctor.get("multi_face_count", 0)),
              str(proctor.get("screen_count", 1))]],
            colWidths=[34*mm]*5)
        pt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), colors.HexColor("#7c3aed")),
            ("TEXTCOLOR",     (0,0),(-1,0), colors.white),
            ("FONTNAME",      (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 8),
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("GRID",          (0,0),(-1,-1), 0.3, colors.HexColor(C["border"])),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ]))
        story += [pt, sp(4)]
        # Flags
        for flag in proctor.get("flags", []):
            story.append(Paragraph(f"<b>!</b> {flag}", body_s))
        story.append(sp(10))

    story.append(Paragraph(
        "PsySense AI -- For internal recruiter use only. Confidential.", cap_s))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────
# MAIN DASHBOARD
# ─────────────────────────────────────────────
RECRUITER_NAV_OPTIONS = ["📋 Candidates", "💼 Jobs", "📈 Analytics"]


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
    [data-testid="stMain"] label,
    [data-testid="stMain"] small,
    [data-testid="stMain"] [data-testid="stWidgetLabel"],
    [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
    [data-testid="stMain"] [data-testid="stCaption"] *,
    [data-testid="stMain"] div[data-testid="stMarkdownContainer"] li {
      color: #374151 !important;
    }
    [data-testid="stMain"] input,
    [data-testid="stMain"] textarea,
    [data-testid="stMain"] [contenteditable="true"] {
      color: #111827 !important;
      -webkit-text-fill-color: #111827 !important;
      background-color: #ffffff !important;
    }
    [data-testid="stMain"] [data-baseweb="select"] div,
    [data-testid="stMain"] [data-baseweb="select"] input {
      color: #111827 !important;
      -webkit-text-fill-color: #111827 !important;
    }
    [data-testid="stMain"] [data-testid="stExpander"] details {
      background: #ffffff !important;
      border: 1px solid #E0E4E8 !important;
      border-radius: 10px !important;
    }
    [data-testid="stMain"] [data-testid="stExpander"] summary,
    [data-testid="stMain"] [data-testid="stExpander"] summary *,
    [data-testid="stMain"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"],
    [data-testid="stMain"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"] * {
      color: #111827 !important;
    }
    [data-testid="stMain"] code {
      color: #111827 !important;
      background: #f1f5f9 !important;
      border-radius: 6px !important;
    }
    [data-testid="stMain"] a {
      color: #2563eb !important;
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
    [data-testid="stMain"] .stButton > button:not([kind="primary"]),
    [data-testid="stMain"] [data-testid="stDownloadButton"] > button,
    [data-testid="stMain"] .stFormSubmitButton > button:not([kind="primary"]) {
      color: #111827 !important;
      -webkit-text-fill-color: #111827 !important;
      background: #ffffff !important;
      border: 1px solid #cbd5e1 !important;
    }
    [data-testid="stMain"] .stButton > button:not([kind="primary"]) *,
    [data-testid="stMain"] [data-testid="stDownloadButton"] > button *,
    [data-testid="stMain"] .stFormSubmitButton > button:not([kind="primary"]) * {
      color: #111827 !important;
      -webkit-text-fill-color: #111827 !important;
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
    .ps-topbar,
    .ps-topbar *,
    .ps-topbar h2,
    .ps-topbar p {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }
    .ps-topbar h2 { margin: 0; font-size: 20px; }
    .ps-topbar p  { margin: 2px 0 0; font-size: 12px; opacity: .86; }

    /* Make Streamlit controls readable on the light dashboard surface. */
    [data-testid="stMain"] [data-baseweb="select"] > div,
    [data-testid="stMain"] [data-baseweb="select"] div[role="combobox"],
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="select"] div[role="combobox"] {
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        box-shadow: none !important;
    }
    [data-testid="stMain"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] [data-baseweb="select"] * {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [data-testid="stMain"] [data-baseweb="select"] svg,
    [data-testid="stSidebar"] [data-baseweb="select"] svg {
        fill: #111827 !important;
        color: #111827 !important;
    }
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [role="listbox"] {
        background: #ffffff !important;
        background-color: #ffffff !important;
        color: #111827 !important;
    }
    [data-baseweb="popover"] *,
    [data-baseweb="menu"] *,
    [role="listbox"] * {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [data-baseweb="popover"] ul,
    [data-baseweb="popover"] li,
    [data-baseweb="popover"] div,
    [data-baseweb="menu"] ul,
    [data-baseweb="menu"] li,
    [data-baseweb="menu"] div,
    [role="listbox"],
    [role="listbox"] div {
        background-color: #ffffff !important;
    }
    [role="option"],
    [role="option"] *,
    [data-baseweb="menu"] * {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [role="option"] {
        background: #ffffff !important;
        background-color: #ffffff !important;
    }
    [role="option"]:hover,
    [role="option"][aria-selected="true"],
    [role="option"][aria-current="true"] {
        background: #eaf3ff !important;
        background-color: #eaf3ff !important;
    }
    [data-testid="stMain"] [role="radiogroup"] label,
    [data-testid="stMain"] [role="radiogroup"] label *,
    [data-testid="stMain"] [data-baseweb="radio"] label,
    [data-testid="stMain"] [data-baseweb="radio"] label * {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] {
        background: #ffffff !important;
        border: 1.5px dashed #cbd5e1 !important;
        border-radius: 10px !important;
    }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] *,
    [data-testid="stMain"] [data-testid="stFileUploaderFile"] *,
    [data-testid="stMain"] [data-testid="stFileUploader"] small,
    [data-testid="stMain"] [data-testid="stFileUploader"] span,
    [data-testid="stMain"] [data-testid="stFileUploader"] p {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
    }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button {
        background: #111827 !important;
        border-color: #111827 !important;
    }
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button,
    [data-testid="stMain"] [data-testid="stFileUploaderDropzone"] button * {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }

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

        st.markdown("**⚙️ Account**")
        can_open_billing = bool(st.session_state.get("org_id"))
        if st.button("Billing & Plan", use_container_width=True, key="sidebar_billing_btn"):
            if can_open_billing:
                st.session_state.show_billing_page = True
                st.rerun()
            else:
                st.warning("Billing is unavailable because this account has no organization.")
        if st.button("Log out", use_container_width=True, key="sidebar_logout_btn"):
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

    _org = st.session_state.get("org_id")
    if st.session_state.get("show_billing_page") and not _org:
        st.session_state.show_billing_page = False
    if st.session_state.get("show_billing_page") and _org:
        b1, b2 = st.columns([1, 4])
        with b1:
            if st.button("Back to dashboard", use_container_width=True, key="billing_back_btn"):
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
    elif nav_mode == "📈 Analytics":
        _show_analytics()


# ─────────────────────────────────────────────
# CANDIDATES OVERVIEW
# ─────────────────────────────────────────────
def _show_invitation_status_panel(job_postings):
    candidates = []
    job_by_id = {p.id: p for p in job_postings}
    for posting in job_postings:
        candidates.extend(get_candidates_by_jd(posting.id))

    st.markdown("### Invitation Status")
    if not candidates:
        st.caption("No invites yet. Create a job, upload resumes, and send invites to track candidates here.")
        st.markdown("---")
        return

    buckets = {"Invited": 0, "Started": 0, "Completed": 0, "Expired": 0}
    for profile in candidates:
        bucket = _invitation_bucket(profile.interview_status)
        if bucket in buckets:
            buckets[bucket] += 1

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Invited", buckets["Invited"])
    m2.metric("Started", buckets["Started"])
    m3.metric("Completed", buckets["Completed"])
    m4.metric("Expired", buckets["Expired"])

    visible = sorted(
        candidates,
        key=lambda p: (
            {"In Progress": 0, "Invited": 1, "Shortlisted": 2, "Expired": 3}.get(p.interview_status or "", 4),
            -(p.id or 0),
        ),
    )[:8]

    with st.expander("View recent invite activity", expanded=True):
        for profile in visible:
            posting = job_by_id.get(profile.jd_id)
            bucket = _invitation_bucket(profile.interview_status)
            badge_class = _invitation_badge_class(bucket)
            deadline = (
                posting.deadline.strftime("%d %b %Y")
                if posting and posting.deadline else "No deadline"
            )
            invited = (
                profile.invite_sent_at.strftime("%d %b %Y")
                if profile.invite_sent_at else "Not sent"
            )
            job_title = posting.title if posting else "Unknown job"
            c1, c2, c3, c4 = st.columns([2.2, 2.1, 1.2, 1.2])
            c1.markdown(
                f"<strong>{html.escape(profile.name or '')}</strong><br/>"
                f"<span style='color:#4b5563'>{html.escape(profile.email or '')}</span>",
                unsafe_allow_html=True,
            )
            c2.markdown(
                f"{html.escape(job_title)}<br/>"
                f"<span style='color:#4b5563'>Deadline: {html.escape(deadline)}</span>",
                unsafe_allow_html=True,
            )
            c3.markdown(
                f'<span class="vbadge {badge_class}">{html.escape(bucket)}</span>',
                unsafe_allow_html=True,
            )
            c4.caption(f"Invited: {invited}")

        remaining = len(candidates) - len(visible)
        if remaining > 0:
            st.caption(f"{remaining} more invite(s) are available under Jobs.")

    st.markdown("---")


def _show_overview():
    org_id = _current_org_id()
    check_expired_invites()
    job_postings = get_job_postings_by_org(org_id)
    _show_invitation_status_panel(job_postings)

    sessions = get_sessions_by_org(org_id)
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

    job_options = ["All Jobs", "No JD"] + [
        f"{p.title} (#{p.id})" for p in job_postings
    ]
    job_id_by_option = {
        f"{p.title} (#{p.id})": p.id for p in job_postings
    }

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
    col_job, col_score, col_risk = st.columns([3, 2, 2])
    with col_job:
        job_filter = st.selectbox("Job", job_options, label_visibility="collapsed")
    with col_score:
        score_filter = st.selectbox(
            "Score",
            ["All Scores", "75+ Strong", "55-74 Good", "35-54 Average", "<35 Needs Work"],
            label_visibility="collapsed",
        )
    with col_risk:
        risk_filter = st.selectbox(
            "Proctoring Risk",
            ["All Risk", "Low", "Medium", "High", "Critical"],
            label_visibility="collapsed",
        )

    filtered = list(sessions)
    if search.strip():
        filtered = [s for s in filtered if search.lower() in s.candidate_name.lower()]
    if status_filter != "All":
        filtered = [s for s in filtered if s.status == status_filter]
    if job_filter == "No JD":
        filtered = [s for s in filtered if not getattr(s, "jd_id", None)]
    elif job_filter != "All Jobs":
        selected_jd_id = job_id_by_option.get(job_filter)
        filtered = [
            s for s in filtered if getattr(s, "jd_id", None) == selected_jd_id
        ]
    if score_filter == "75+ Strong":
        filtered = [s for s in filtered if (s.final_score or 0) >= 75]
    elif score_filter == "55-74 Good":
        filtered = [s for s in filtered if 55 <= (s.final_score or 0) < 75]
    elif score_filter == "35-54 Average":
        filtered = [s for s in filtered if 35 <= (s.final_score or 0) < 55]
    elif score_filter == "<35 Needs Work":
        filtered = [s for s in filtered if (s.final_score or 0) < 35]
    if risk_filter != "All Risk":
        filtered = [
            s for s in filtered
            if (getattr(s, "proctoring_risk", "Low") or "Low") == risk_filter
        ]
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
    active_filters = [
        label for label in (job_filter, score_filter, risk_filter)
        if label not in ("All Jobs", "All Scores", "All Risk")
    ]
    if active_filters:
        st.caption("Filters: " + " · ".join(active_filters))

    STATUS_ICON = {"Pending": "🕐", "Shortlisted": "⭐", "Rejected": "❌"}
    BADGE_CLASS = {"Strong Advance": "vb-green", "Advance": "vb-blue",
                   "Borderline": "vb-yellow",    "Do Not Advance": "vb-red"}

    for s in filtered:
        sc      = s.final_score or 0
        emoji   = "🟢" if sc >= 75 else ("🟡" if sc >= 55 else "🔴")
        verdict = _verdict_from_score(s.cognitive_score or 5.0)
        decision, decision_class = _decision_for_session(s)
        bc      = BADGE_CLASS.get(verdict, "vb-yellow")
        si      = STATUS_ICON.get(s.status, "")
        insight_data = _safe_json_loads(s.insight_json, {})

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2.8, 0.9, 1.1, 1.2, 1.0])
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
                f'<span class="vbadge {decision_class}">{decision}</span>',
                unsafe_allow_html=True)

            # Proctoring risk badge
            _proctor_risk = getattr(s, 'proctoring_risk', 'Low') or 'Low'
            _proctor_color = {"Low": "#16a34a", "Medium": "#d97706", "High": "#dc2626", "Critical": "#7f1d1d"}.get(_proctor_risk, "#6B7280")
            _proctor_icon = {"Low": "&#x1F6E1;", "Medium": "&#x26A0;", "High": "&#x1F6A8;", "Critical": "&#x1F6D1;"}.get(_proctor_risk, "")
            _tab_ct = getattr(s, 'tab_switch_count', 0) or 0

            c4.markdown(
                f'<p style="color:#374151;font-size:12px;margin:0">'
                f"{html.escape(s.created_at.strftime('%d %b %Y'))}<br/>"
                f'<span style="color:{_proctor_color};font-size:11px;font-weight:600">'
                f'{_proctor_icon} {_proctor_risk}'
                f'{"" if _tab_ct == 0 else f" ({_tab_ct} tab)"}'
                f'</span></p>',
                unsafe_allow_html=True,
            )
            c5.markdown(
                f'<span class="vbadge {bc}">{_verdict_badge(verdict)}</span>',
                unsafe_allow_html=True)

            b1, b2, b3 = st.columns([1.5, 1, 1])
            with b1:
                if st.button("📄 Full Report", key=f"view_{s.id}"):
                    st.session_state.recruiter_detail_id = s.id
                    st.rerun()
            with b2:
                st.download_button(
                    "⬇ PDF", data=generate_candidate_pdf(s.id, org_id),
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
    org_id = _current_org_id()
    s = get_session_by_id_for_org(session_id, org_id)
    if not s:
        st.error("Candidate not found or not available for this recruiter account.")
        st.session_state.recruiter_detail_id = None
        return

    insight  = _safe_json_loads(s.insight_json, {})
    per_q    = _safe_json_loads(s.per_question_json, [])
    verdicts = _safe_json_loads(s.recruiter_verdicts_json, [])

    sc      = s.final_score or 0
    verdict = _verdict_from_score(s.cognitive_score or 5.0)
    vc      = _verdict_color(verdict)
    proctor = _safe_json_loads(getattr(s, "proctoring_json", None), {})
    risk = proctor.get("risk_level", getattr(s, "proctoring_risk", "Low") or "Low") if proctor else (getattr(s, "proctoring_risk", "Low") or "Low")
    risk_color = {
        "Low": C["primary"],
        "Medium": C["accent"],
        "High": C["danger"],
        "Critical": "#7f1d1d",
    }.get(risk, C["muted"])

    if verdict in ("Strong Advance", "Advance") and risk in ("Low", "Medium"):
        decision = "Advance"
        decision_note = "Candidate looks suitable for the next hiring step."
        decision_color = C["primary"]
    elif verdict == "Do Not Advance" or sc < 45:
        decision = "Reject"
        decision_note = "Candidate does not currently meet the role signal threshold."
        decision_color = C["danger"]
    else:
        decision = "Hold"
        decision_note = "Review answers and proctoring context before deciding."
        decision_color = C["accent"]

    strengths = [str(x) for x in insight.get("strengths", []) if x][:2]
    weaknesses = [str(x) for x in insight.get("weaknesses", []) if x][:2]
    if not strengths:
        if (s.cognitive_score or 0) >= 6:
            strengths.append("Relevant answer quality")
        if (s.engagement_score or 0) >= 6:
            strengths.append("Good attentiveness")
    if not weaknesses:
        if (s.cognitive_score or 0) < 6:
            weaknesses.append("Answer quality needs review")
        if (s.engagement_score or 0) < 6:
            weaknesses.append("Attentiveness signal needs review")
    if risk in ("High", "Critical"):
        weaknesses.insert(0, f"{risk} proctoring risk")
    strengths = strengths[:2] or ["No major strength detected"]
    weaknesses = weaknesses[:2] or ["No major concern detected"]
    next_action = {
        "Advance": "Shortlist or schedule the next round.",
        "Hold": "Open question breakdown and add recruiter notes.",
        "Reject": "Mark rejected or keep notes for audit.",
    }[decision]

    h1, h2 = st.columns([4, 1])
    with h1:
        st.markdown(f"## 📋 {s.candidate_name}")
        st.caption(
            f"📅 {s.created_at.strftime('%d %b %Y, %H:%M')} · "
            f"🎤 {s.questions_answered} questions · "
            f"{'JD ✓' if s.jd_used else 'No JD'} · ID #{s.id}")
    with h2:
        st.download_button(
            "⬇ PDF", data=generate_candidate_pdf(session_id, org_id),
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

    st.markdown(f"""
    <div style="background:#fff;border:1px solid {C['border']};border-radius:12px;
         padding:18px 20px;margin:14px 0 18px;box-shadow:0 1px 3px rgba(15,23,42,0.06)">
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;
           flex-wrap:wrap;margin-bottom:14px">
        <div>
          <div style="font-size:11px;font-weight:700;color:{C['muted']};
               text-transform:uppercase;letter-spacing:.6px">Decision Summary</div>
          <div style="font-size:24px;font-weight:800;color:{decision_color};line-height:1.25">
            {html.escape(decision)}
          </div>
          <div style="font-size:13px;color:#374151;margin-top:3px">
            {html.escape(decision_note)}
          </div>
        </div>
        <div style="text-align:right">
          <div style="font-size:11px;font-weight:700;color:{C['muted']};
               text-transform:uppercase;letter-spacing:.6px">Proctoring</div>
          <div style="font-size:18px;font-weight:800;color:{risk_color}">
            {html.escape(risk)}
          </div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px">
        <div style="border-top:1px solid {C['border']};padding-top:12px">
          <div style="font-size:12px;font-weight:700;color:{C['primary']};margin-bottom:6px">
            Top Strengths
          </div>
          <div style="font-size:13px;color:#111827;line-height:1.6">
            1. {html.escape(strengths[0])}<br>
            2. {html.escape(strengths[1] if len(strengths) > 1 else strengths[0])}
          </div>
        </div>
        <div style="border-top:1px solid {C['border']};padding-top:12px">
          <div style="font-size:12px;font-weight:700;color:{C['danger']};margin-bottom:6px">
            Main Concerns
          </div>
          <div style="font-size:13px;color:#111827;line-height:1.6">
            1. {html.escape(weaknesses[0])}<br>
            2. {html.escape(weaknesses[1] if len(weaknesses) > 1 else weaknesses[0])}
          </div>
        </div>
        <div style="border-top:1px solid {C['border']};padding-top:12px">
          <div style="font-size:12px;font-weight:700;color:{C['secondary']};margin-bottom:6px">
            Next Action
          </div>
          <div style="font-size:13px;color:#111827;line-height:1.6">
            {html.escape(next_action)}
          </div>
        </div>
      </div>
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
            x=["Answer Quality", "Delivery Signal", "Attentiveness"],
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
            ("Delivery Signal", "emotion",    C["accent"]),
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
                m2.metric("Delivery Signal", f"{round(qd.get('emotion',5),1)}/10")
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
                    s1.metric("Delivery",     f"{sb.get('delivery_model', sb.get('emotion_model',5))}/10")
                    s2.metric("Fluency",      f"{sb.get('fluency_score',5)}/10")
                    s3.metric("Voice Consistency", f"{sb.get('voice_score',5)}/10")

# ─────────────────────────────────────────────
# STUDENTS
# ─────────────────────────────────────────────
def _show_registered_students():
    st.info("Student management was removed from the recruiter dashboard. Use Candidates and Jobs instead.")


# ─────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────
def _show_analytics():
    st.markdown("### 📈 Advanced Analytics")
    org_id = _current_org_id()
    sessions = get_sessions_by_org(org_id)
    postings = get_job_postings_by_org(org_id)
    posting_stats = [get_jd_stats(p.id) for p in postings]

    invited = sum(s.get("Invited", 0) for s in posting_stats)
    in_progress = sum(s.get("In Progress", 0) for s in posting_stats)
    completed_profiles = sum(s.get("Completed", 0) for s in posting_stats)
    passed_profiles = sum(s.get("Passed", 0) for s in posting_stats)
    below_profiles = sum(s.get("Below Threshold", 0) for s in posting_stats)
    expired_profiles = sum(s.get("Expired", 0) for s in posting_stats)
    shortlisted_profiles = sum(s.get("Shortlisted", 0) for s in posting_stats)
    completed_sessions = len(sessions)
    completed_total = max(completed_profiles + passed_profiles + below_profiles, completed_sessions)

    if not sessions and not postings:
        st.info("No data yet.")
        return

    st.markdown("#### Hiring Funnel")
    f1, f2, f3, f4, f5, f6 = st.columns(6)
    f1.metric("Jobs", len(postings))
    f2.metric("Invited", invited)
    f3.metric("In Progress", in_progress)
    f4.metric("Completed", completed_total)
    f5.metric("Passed", passed_profiles)
    f6.metric("Shortlisted", shortlisted_profiles)

    funnel_labels = ["Invited", "In Progress", "Completed", "Passed", "Shortlisted"]
    funnel_values = [invited, in_progress, completed_total, passed_profiles, shortlisted_profiles]
    fig_funnel = go.Figure(go.Bar(
        x=funnel_labels,
        y=funnel_values,
        marker_color=[C["secondary"], C["info"], C["primary"], "#16a34a", C["accent"]],
        text=funnel_values,
        textposition="outside",
    ))
    fig_funnel.update_layout(
        height=280,
        showlegend=False,
        yaxis_title="Candidates",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=30),
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    if expired_profiles:
        st.caption(f"{expired_profiles} invite(s) expired.")

    if not sessions:
        st.info("No completed interviews yet. Funnel data will update as candidates finish interviews.")
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
        "Delivery Signal": sum(s.emotion_score    or 0 for s in sessions) / n,
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
