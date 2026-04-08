"""
app.py — PsySense AI Mock Interview (v4 — Professional Camera UI)

UI changes vs v3:
- Camera panel styled like HireVue/Karat: dark "monitor" chrome, name plate,
  animated REC indicator, live metric chips inside the camera frame
- Camera column uses dark #0d0d14 bg so video feels immersive / professional
- Engagement/Presence/Emotion shown as styled chips INSIDE the camera panel
- Global design tokens via CSS :root variables — consistent everywhere
- JetBrains Mono used for all numeric readouts (timers, metrics)
- STOP button fully suppressed (CSS + JS)
- Phase routing: correct if/elif/else (no start-screen bleed)

Logic: UNCHANGED from v3.
"""

import streamlit as st
import requests
import time

from database import init_db, verify_login, register_student, save_session, get_all_sessions
from recruiter_dashboard import show_recruiter_dashboard
from whisper_audio import record_answer_background
from voice_question import speak_question
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode
from engagement_realtime import EngagementDetector
import av

init_db()

st.set_page_config(
    page_title="PsySense — AI Interview",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM  +  GLOBAL STYLES
# ══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Design tokens ── */
:root {
  --bg:         #f5f5f9;
  --surface:    #ffffff;
  --border:     #e4e4ec;
  --border-mid: #d0d0dc;
  --navy:       #0f0f1e;
  --navy-mid:   #1a1a2e;
  --indigo:     #4f46e5;
  --muted:      #72728a;
  --text:       #18181f;
  --cam-bg:     #0d0d14;
  --cam-border: #252535;
  --red:        #ef4444;
  --green:      #22c55e;
  --amber:      #f59e0b;
  --r-card:     14px;
  --shadow:     0 1px 3px rgba(0,0,0,0.06),0 1px 2px rgba(0,0,0,0.04);
  --shadow-lg:  0 4px 20px rgba(0,0,0,0.10),0 1px 6px rgba(0,0,0,0.06);
  --mono:       'JetBrains Mono', 'Fira Code', monospace;
}

html, body, [class*="css"] {
  font-family: 'DM Sans', -apple-system, sans-serif !important;
  -webkit-font-smoothing: antialiased !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stSidebarNav"] { display: none !important; }

/* ══ STOP BUTTON — complete suppression ══ */
button[kind="secondary"],
button[data-testid="baseButton-secondary"],
div[data-testid="stWebRtcStreamer"] button:not(:first-child),
.stWebRtcStreamer button[kind] {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
  width: 0 !important; height: 0 !important;
  overflow: hidden !important;
  position: absolute !important; top: -9999px !important;
}

/* ── App bg ── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main { background: var(--bg) !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 220px !important; max-width: 220px !important;
}
[data-testid="stSidebar"] .stButton > button { width: 100% !important; font-size: 13px !important; }

/* ── Cards ── */
.ps-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-card);
  padding: 20px 22px;
  margin-bottom: 14px;
  box-shadow: var(--shadow);
}
.ps-inset {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 10px;
}

/* ── Stepper ── */
.ps-stepper {
  display: flex; align-items: center; gap: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-card);
  padding: 12px 20px;
  margin-bottom: 24px;
  overflow-x: auto;
  box-shadow: var(--shadow);
}
.ps-step { display: flex; align-items: center; gap: 8px; }
.ps-step-num {
  width: 26px; height: 26px; border-radius: 50%;
  font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; line-height: 1;
}
.ps-num-done   { background: var(--navy-mid); color: #fff; }
.ps-num-active { background: var(--indigo); color: #fff; box-shadow: 0 0 0 4px rgba(79,70,229,0.15); }
.ps-num-todo   { background: #f0f0f6; color: #a0a0b4; border: 1px solid var(--border); }
.ps-lbl        { font-size: 12px; font-weight: 500; color: #8888a0; white-space: nowrap; }
.ps-lbl-active { color: var(--indigo); font-weight: 700; }
.ps-lbl-done   { color: var(--navy-mid); font-weight: 600; }
.ps-line       { width: 28px; height: 1px; background: var(--border); margin: 0 6px; flex-shrink: 0; }
.ps-line-done  { background: var(--navy-mid); }

/* ── Primary button ── */
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] button {
  background: var(--navy-mid) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 10px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 600 !important; font-size: 14px !important;
  padding: 11px 22px !important;
  height: auto !important; min-height: 42px !important;
  width: 100% !important; letter-spacing: -0.1px !important;
  transition: opacity .15s, transform .1s !important;
}
.stButton > button[kind="primary"]:hover   { opacity: .85 !important; transform: translateY(-1px) !important; }
.stButton > button[kind="primary"]:active  { transform: scale(.98) !important; }

/* ── Secondary button ── */
.stButton > button:not([kind="primary"]) {
  background: var(--surface) !important;
  color: var(--navy-mid) !important;
  border: 1px solid var(--border-mid) !important;
  border-radius: 10px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 500 !important; font-size: 14px !important;
  padding: 11px 22px !important;
  height: auto !important; min-height: 42px !important;
  transition: background .12s !important;
}
.stButton > button:not([kind="primary"]):hover { background: var(--bg) !important; }

/* ── Inputs ── */
.stTextInput input, .stTextArea textarea {
  background: var(--surface) !important;
  border: 1px solid var(--border-mid) !important;
  border-radius: 9px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-size: 14px !important; color: var(--text) !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
  border-color: var(--indigo) !important;
  box-shadow: 0 0 0 3px rgba(79,70,229,0.10) !important;
  outline: none !important;
}
.stTextInput label, .stTextArea label {
  color: var(--muted) !important; font-weight: 500 !important; font-size: 13px !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] > div {
  background: #fafafa !important;
  border: 1.5px dashed #c4c4d4 !important;
  border-radius: 12px !important;
}
[data-testid="stFileUploader"]:hover > div { border-color: var(--indigo) !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
  background: #ededf3 !important;
  border-radius: 12px !important; padding: 4px !important;
  gap: 2px !important; border: none !important;
}
.stTabs [data-baseweb="tab"] {
  border-radius: 9px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-size: 14px !important; font-weight: 500 !important;
  color: #666677 !important; border: none !important;
  background: transparent !important; padding: 8px 18px !important;
}
.stTabs [aria-selected="true"] {
  background: var(--surface) !important;
  color: var(--navy-mid) !important; font-weight: 600 !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.09) !important;
}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] { display: none !important; }

/* ── Progress bar ── */
.stProgress > div > div {
  background: #e4e4ee !important; border-radius: 6px !important; height: 5px !important;
}
.stProgress > div > div > div { background: var(--indigo) !important; border-radius: 6px !important; }

/* ── Metric cards ── */
[data-testid="stMetric"] {
  background: var(--surface) !important; border: 1px solid var(--border) !important;
  border-radius: 12px !important; padding: 14px 16px !important;
  box-shadow: var(--shadow) !important;
}
[data-testid="stMetricLabel"] > div { color: var(--muted) !important; font-size: 12px !important; font-weight: 600 !important; }
[data-testid="stMetricValue"] > div { color: var(--navy-mid) !important; font-size: 22px !important; font-weight: 700 !important; }

/* ── Alerts ── */
[data-testid="stSuccess"] { border-radius: 10px !important; border: 1px solid #b6f0cc !important; background: #effaf4 !important; color: #166534 !important; }
[data-testid="stWarning"] { border-radius: 10px !important; background: #fffbeb !important; border: 1px solid #fde68a !important; color: #92400e !important; }
[data-testid="stError"]   { border-radius: 10px !important; background: #fef2f2 !important; border: 1px solid #fecaca !important; color: #991b1b !important; }
[data-testid="stInfo"]    { border-radius: 10px !important; background: #eff6ff !important; border: 1px solid #bfdbfe !important; color: #1e40af !important; }
[data-testid="stForm"] { background: transparent !important; border: none !important; padding: 0 !important; }

/* ── Radio ── */
.stRadio > div { gap: 10px !important; }
.stRadio [data-testid="stMarkdownContainer"] p { color: #444455 !important; font-size: 13px !important; }

/* ── WebRTC video ── */
div[data-testid="stWebRtcStreamer"],
div[data-testid="stWebRtcStreamer"] > div { width: 100% !important; }
div[data-testid="stWebRtcStreamer"] video {
  width: 100% !important; height: auto !important;
  display: block !important; border-radius: 0 !important;
}

/* ── START button inside WebRTC ── */
div[data-testid="stWebRtcStreamer"] button:first-child {
  background: var(--indigo) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 8px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 600 !important;
  font-size: 13px !important;
  padding: 8px 18px !important;
  width: 100% !important;
  margin-top: 6px !important;
}

/* ── Divider ── */
hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 18px 0 !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: var(--indigo) !important; }

/* ── Animations ── */
@keyframes rec-blink  { 0%,100%{opacity:1} 50%{opacity:.2} }
@keyframes ps-blink   { 0%,100%{opacity:1} 50%{opacity:.15} }
</style>

<script>
(function () {
  const kill = () => {
    document.querySelectorAll('button').forEach(b => {
      if (b.textContent.trim() === 'STOP') {
        b.style.cssText = 'display:none!important;visibility:hidden!important;' +
          'pointer-events:none!important;height:0!important;width:0!important;' +
          'position:absolute!important;top:-9999px!important;';
      }
    });
    document.querySelectorAll('[data-testid="stWebRtcStreamer"] button').forEach(b => {
      if (b.textContent.trim() !== 'START') b.style.cssText = 'display:none!important;';
    });
  };
  kill();
  setInterval(kill, 250);
  new MutationObserver(kill).observe(document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════
STEPS = ["Setup", "Camera Check", "Interview", "Complete"]

def render_stepper(active: int):
    parts = []
    for i, lbl in enumerate(STEPS):
        if i < active:
            nc, ni, lc = "ps-step-num ps-num-done", "✓", "ps-lbl ps-lbl-done"
        elif i == active:
            nc, ni, lc = "ps-step-num ps-num-active", str(i+1), "ps-lbl ps-lbl-active"
        else:
            nc, ni, lc = "ps-step-num ps-num-todo", str(i+1), "ps-lbl"
        parts.append(
            f'<div class="ps-step"><div class="{nc}">{ni}</div>'
            f'<span class="{lc}">{lbl}</span></div>'
        )
        if i < len(STEPS) - 1:
            lnc = "ps-line ps-line-done" if i < active else "ps-line"
            parts.append(f'<div class="{lnc}"></div>')
    st.markdown(f'<div class="ps-stepper">{"".join(parts)}</div>', unsafe_allow_html=True)


def page_title(t: str, sub: str = ""):
    sub_h = (f'<p style="font-size:13px;color:var(--muted);margin:3px 0 0;font-weight:400">{sub}</p>'
             if sub else "")
    st.markdown(
        f'<h2 style="font-size:21px;font-weight:700;color:var(--text);'
        f'letter-spacing:-0.3px;margin:0 0 2px">{t}</h2>{sub_h}',
        unsafe_allow_html=True)


def q_label(num, total, suffix=""):
    suf = f" — {suffix}" if suffix else ""
    st.markdown(
        f'<div style="font-size:11px;font-weight:600;letter-spacing:0.7px;'
        f'color:#9999ae;text-transform:uppercase;margin-bottom:10px">'
        f'Question {num} of {total}{suf}</div>',
        unsafe_allow_html=True)


def _metric_color(val, hi, lo, invert=False):
    if not invert:
        if val >= hi: return "#4ade80"
        if val >= lo: return "#fbbf24"
        return "#f87171"
    else:
        if val <= lo: return "#4ade80"
        if val <= hi: return "#fbbf24"
        return "#f87171"


# ══════════════════════════════════════════════════════════════════════════
# WEBCAM PROCESSOR
# ══════════════════════════════════════════════════════════════════════════
class EngagementProcessor(VideoProcessorBase):
    def __init__(self):
        self.detector = EngagementDetector()

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        return av.VideoFrame.from_ndarray(self.detector.process_frame(img), format="bgr24")

    def get_avg_score(self):       return self.detector.get_avg_score()
    def set_countdown(self, v):    self.detector.set_countdown(v)
    def get_absence_ratio(self):   return self.detector.get_absence_ratio()
    def get_emotion_summary(self): return self.detector.get_emotion_summary()

    def snapshot_and_reset(self):
        s = self.detector.get_avg_score()
        a = self.detector.get_absence_ratio()
        e = self.detector.get_emotion_summary()
        self.detector.reset_session()
        return s, a, e


PREP_TIME   = 15
RECORD_TIME = 60

# ══════════════════════════════════════════════════════════════════════════
# SESSION DEFAULTS
# ══════════════════════════════════════════════════════════════════════════
_D = {
    "logged_in": False, "user_role": None,
    "auth_username": "", "auth_display_name": "",
    "recruiter_detail_id": None, "recruiter_view_users": False,
    "phase": "start", "q_index": 0,
    "candidate_name": "", "questions": [], "resume_text": "", "jd_text": "",
    "question_spoken": False, "session_saved": False,
    "saved_session_id": None, "webhook_sent": False,
    "prep_start": None, "record_start": None, "retry_used": False,
    "record_container": {"text": "", "done": False, "wav_path": None, "duration": 60},
    "answer_input": "",
    "cognitive_scores": [], "emotion_scores": [], "engagement_scores": [],
    "absence_ratios": [], "low_presence_flags": [],
    "question_history": [], "answer_history": [],
    "recruiter_verdicts": [], "dimension_scores": [],
    "cur_engagement": None, "cur_absence": None,
    "cur_facial_emotion": {"dominant": "neutral", "breakdown": {}},
    "speech_breakdowns": [], "facial_emotions": [],
}
for k, v in _D.items():
    if k not in st.session_state:
        st.session_state[k] = v


def go_to(p):
    st.session_state.phase = p
    st.rerun()

def _logout():
    st.session_state.clear()
    st.rerun()

def _new_interview():
    keep = {k: st.session_state[k] for k in
            ["logged_in", "user_role", "auth_username", "auth_display_name"]}
    st.session_state.clear()
    for k, v in _D.items():
        st.session_state[k] = v
    st.session_state.update(keep)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
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
        tab_in, tab_reg = st.tabs(["Sign In", "Create Account"])

        with tab_in:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            with st.form("login_form"):
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
                        st.session_state.logged_in         = True
                        st.session_state.user_role         = user["role"]
                        st.session_state.auth_username     = user["username"]
                        st.session_state.auth_display_name = user["display_name"]
                        if user["role"] == "student":
                            st.session_state.candidate_name = user["display_name"]
                        st.rerun()
                    else:
                        st.error("Incorrect username or password.")

            st.markdown("""
            <div style="margin-top:16px;padding:11px 14px;background:var(--bg);
                 border-radius:9px;border:1px solid var(--border)">
              <div style="font-size:10px;color:#aaaabc;font-weight:700;
                   text-transform:uppercase;letter-spacing:0.8px;margin-bottom:5px">Demo recruiter</div>
              <div style="font-size:12px;color:var(--muted);font-family:var(--mono)">
                user: <b style="color:var(--text)">recruiter</b>
                &nbsp;·&nbsp; pass: <b style="color:var(--text)">admin123</b>
              </div>
            </div>
            """, unsafe_allow_html=True)

        with tab_reg:
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            with st.form("register_form"):
                r_name  = st.text_input("Full Name",        placeholder="Arjun Sharma")
                r_user  = st.text_input("Username",         placeholder="arjun_sharma")
                r_email = st.text_input("Email (optional)", placeholder="arjun@email.com")
                r_pass  = st.text_input("Password",         type="password", placeholder="min 8 chars")
                r_conf  = st.text_input("Confirm",          type="password", placeholder="repeat password")
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                reg_sub = st.form_submit_button("Create Account →", use_container_width=True)
            if reg_sub:
                if not r_name or not r_user or not r_pass:
                    st.warning("Name, username and password are required.")
                elif r_pass != r_conf:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = register_student(r_user.strip(), r_pass, r_name.strip(), r_email.strip())
                    (st.success if ok else st.error)(msg)
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    role_label = "🏢 Recruiter" if st.session_state.user_role == "recruiter" else "🎤 Candidate"
    st.markdown(f"""
    <div style="padding:6px 0 14px">
      <div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;
           letter-spacing:0.8px;margin-bottom:8px">{role_label}</div>
      <div style="font-size:15px;font-weight:700;color:var(--text);line-height:1.2">
        {st.session_state.auth_display_name}</div>
      <div style="font-size:12px;color:var(--muted);margin-top:3px">
        @{st.session_state.auth_username}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    if st.session_state.user_role != "recruiter":
        phase_map = {
            "start": "Setting up", "camera_setup": "Camera check",
            "prep": "Preparing", "recording": "Recording",
            "processing": "Processing", "transcript": "Reviewing", "report": "Completed",
        }
        cur = phase_map.get(st.session_state.phase, "In progress")
        st.markdown(f"""
        <div style="padding:10px 12px;background:var(--bg);border-radius:9px;
             border:1px solid var(--border);margin-bottom:14px">
          <div style="font-size:10px;font-weight:600;color:#aaaabc;
               text-transform:uppercase;letter-spacing:0.6px;margin-bottom:4px">Status</div>
          <div style="font-size:13px;font-weight:600;color:var(--text)">{cur}</div>
        </div>
        """, unsafe_allow_html=True)
    if st.button("🚪  Logout", use_container_width=True, key="sb_logout"):
        _logout()

if st.session_state.user_role != "recruiter":
    st.markdown('<style>[data-testid="stSidebarNav"]{display:none!important}</style>',
                unsafe_allow_html=True)

if st.session_state.user_role == "recruiter":
    show_recruiter_dashboard()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# TOP BAR
# ══════════════════════════════════════════════════════════════════════════
phase     = st.session_state.phase
QUESTIONS = st.session_state.get("questions", [])

st.markdown("""
<div style="display:flex;align-items:center;gap:10px;padding-bottom:16px;
     margin-bottom:20px;border-bottom:1px solid var(--border)">
  <div style="width:34px;height:34px;background:var(--navy-mid);border-radius:9px;
       display:inline-flex;align-items:center;justify-content:center;
       font-size:12px;font-weight:800;color:#fff;flex-shrink:0">PS</div>
  <div>
    <div style="font-size:15px;font-weight:700;color:var(--text);line-height:1">PsySense</div>
    <div style="font-size:11px;color:var(--muted)">AI Mock Interview</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# PHASE ROUTING  —  if / elif / else  (one branch per render pass)
# ══════════════════════════════════════════════════════════════════════════

# ── START ─────────────────────────────────────────────────────────────────
if phase == "start":
    render_stepper(0)
    page_title(f"Welcome, {st.session_state.auth_display_name} 👋",
               "Upload your resume to get 5 personalised interview questions.")
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    left, right = st.columns([1.05, 1], gap="large")

    with left:
        st.markdown("""
        <div class="ps-card">
          <div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;
               letter-spacing:0.8px;margin-bottom:6px">Required · Step 1</div>
          <div style="font-size:16px;font-weight:700;color:var(--text);margin-bottom:4px">
            Upload Your Resume</div>
          <div style="font-size:13px;color:var(--muted);margin-bottom:14px;line-height:1.6">
            The AI reads your background and creates 5 tailored questions.</div>
        </div>
        """, unsafe_allow_html=True)
        resume_file = st.file_uploader("Resume PDF", type=["pdf"], label_visibility="collapsed")
        if resume_file:
            st.markdown(
                f'<div style="font-size:12px;color:#16a34a;font-weight:600;margin-top:6px">'
                f'✓ &nbsp;{resume_file.name}</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.markdown('<div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;'
                    'letter-spacing:0.8px;margin-bottom:6px">Your name for the report</div>',
                    unsafe_allow_html=True)
        candidate_name = st.text_input(
            "Name",
            value=st.session_state.candidate_name or st.session_state.auth_display_name,
            label_visibility="collapsed")

    with right:
        st.markdown("""
        <div class="ps-card">
          <div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;
               letter-spacing:0.8px;margin-bottom:6px">Optional · Step 2</div>
          <div style="font-size:16px;font-weight:700;color:var(--text);margin-bottom:4px">
            Job Description</div>
          <div style="font-size:13px;color:var(--muted);margin-bottom:14px;line-height:1.6">
            Adds role-fit scoring. Answers evaluated against the actual requirements.</div>
        </div>
        """, unsafe_allow_html=True)
        jd_mode       = st.radio("JD mode", ["Paste text", "Upload PDF"],
                                  horizontal=True, label_visibility="collapsed")
        jd_text_input = ""
        jd_pdf_text   = ""
        if jd_mode == "Paste text":
            jd_text_input = st.text_area(
                "Job description", height=120,
                placeholder="Paste the job description here…",
                label_visibility="collapsed")
        else:
            jd_file = st.file_uploader("JD PDF", type=["pdf"],
                                        label_visibility="collapsed", key="jd_up")
            if jd_file:
                import tempfile, os
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t:
                    t.write(jd_file.read()); tp = t.name
                from resume_parser import extract_jd_text
                jd_pdf_text = extract_jd_text(tp)
                try: os.unlink(tp)
                except: pass
                (st.success(f"✓ JD extracted — {len(jd_pdf_text):,} chars") if jd_pdf_text
                 else st.warning("Could not extract text from PDF."))

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    _, cta, _ = st.columns([0.4, 1, 0.4])
    with cta:
        if st.button("Generate Questions & Start Interview →",
                     type="primary", use_container_width=True):
            if not candidate_name.strip():
                st.warning("Please enter your name.")
            elif not resume_file:
                st.warning("Please upload your resume PDF.")
            else:
                st.session_state.candidate_name = candidate_name.strip()
                final_jd = (jd_pdf_text or jd_text_input or "").strip()
                st.session_state.jd_text = final_jd
                import tempfile, os
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t:
                    t.write(resume_file.read()); tp = t.name
                with st.spinner("Reading resume and crafting personalised questions…"):
                    from resume_parser import extract_resume_text, generate_questions
                    rt = extract_resume_text(tp)
                    qs = generate_questions(rt, jd_text=final_jd)
                try: os.unlink(tp)
                except: pass
                st.session_state.questions   = qs
                st.session_state.resume_text = rt
                st.success(f"✓ {len(qs)} questions ready ({'resume + JD' if final_jd else 'resume only'})")
                time.sleep(0.8)
                go_to("camera_setup")


# ── REPORT ────────────────────────────────────────────────────────────────
elif phase == "report":
    render_stepper(3)

    n       = max(len(st.session_state.cognitive_scores), 1)
    avg_cog = sum(st.session_state.cognitive_scores) / n
    avg_emo = sum(st.session_state.emotion_scores)   / max(len(st.session_state.emotion_scores), 1)
    avg_eng = sum(st.session_state.engagement_scores)/ max(len(st.session_state.engagement_scores), 1)

    try:
        fr = requests.post("http://127.0.0.1:8001/fuse",
            json={"cognitive_score": avg_cog, "emotion_score": avg_emo,
                  "engagement_score": avg_eng}, timeout=10).json()
    except:
        fr = {"final_behavioral_score": round((0.5*avg_cog + 0.3*avg_emo + 0.2*avg_eng)*10, 1)}

    try:
        ir = requests.post("http://127.0.0.1:8003/generate_insight",
            json={"avg_cognitive": avg_cog, "avg_emotion": avg_emo,
                  "avg_engagement": avg_eng, "final_score": fr["final_behavioral_score"]},
            timeout=30).json()
    except:
        ir = {"strengths": [], "weaknesses": [], "recommendation": "N/A"}

    final_score = fr["final_behavioral_score"]

    if not st.session_state.get("session_saved", False):
        pq = []
        for i in range(len(st.session_state.question_history)):
            pq.append({
                "question":       st.session_state.question_history[i],
                "answer":         st.session_state.answer_history[i],
                "cognitive":      st.session_state.cognitive_scores[i],
                "emotion":        st.session_state.emotion_scores[i],
                "engagement":     st.session_state.engagement_scores[i],
                "absence":        st.session_state.absence_ratios[i]     if i < len(st.session_state.absence_ratios)    else 0.0,
                "verdict":        st.session_state.recruiter_verdicts[i] if i < len(st.session_state.recruiter_verdicts) else "",
                "dimensions":     st.session_state.dimension_scores[i]  if i < len(st.session_state.dimension_scores)   else {},
                "speech":         st.session_state.speech_breakdowns[i] if i < len(st.session_state.speech_breakdowns)  else {},
                "facial_emotion": st.session_state.facial_emotions[i]   if i < len(st.session_state.facial_emotions)    else {},
            })
        sid = save_session(
            candidate_name=st.session_state.candidate_name, username=st.session_state.auth_username,
            final_score=final_score, cognitive_score=avg_cog, emotion_score=avg_emo,
            engagement_score=avg_eng, questions_answered=len(st.session_state.question_history),
            insight_data=ir, per_question_data=pq, jd_used=bool(st.session_state.get("jd_text")),
            recruiter_verdicts=st.session_state.recruiter_verdicts)
        st.session_state.session_saved    = True
        st.session_state.saved_session_id = sid

        if not st.session_state.get("webhook_sent", False):
            try:
                import datetime as _dt
                requests.post("http://localhost:5678/webhook/psysense-interview", json={
                    "candidate_name": st.session_state.candidate_name, "final_score": final_score,
                    "cognitive_score": round(avg_cog,1), "emotion_score": round(avg_emo,1),
                    "engagement_score": round(avg_eng,1),
                    "questions_answered": len(st.session_state.question_history),
                    "flagged": final_score < 50, "status": "Pending",
                    "interview_date": _dt.datetime.now().strftime("%d %b %Y, %H:%M"),
                    "username": st.session_state.auth_username}, timeout=5)
                st.session_state.webhook_sent = True
            except Exception as _e:
                print(f"[n8n] ⚠️ Webhook failed: {_e}", flush=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    _, hero_col, _ = st.columns([0.5, 2, 0.5])
    with hero_col:
        st.markdown(f"""
        <div style="text-align:center;padding:32px 24px;background:var(--surface);
             border-radius:20px;border:1px solid var(--border);margin-bottom:20px;
             box-shadow:var(--shadow-lg)">
          <div style="width:72px;height:72px;background:#effaf4;border-radius:50%;
               display:inline-flex;align-items:center;justify-content:center;
               font-size:32px;margin-bottom:16px;border:1px solid #b6f0cc">✅</div>
          <h2 style="font-size:24px;font-weight:800;color:var(--text);letter-spacing:-0.5px;
               margin:0 0 10px">Interview Complete!</h2>
          <p style="font-size:14px;color:var(--muted);line-height:1.65;margin:0 0 16px">
            Thank you, <strong>{st.session_state.candidate_name}</strong>.
            Your responses have been saved and submitted for recruiter review.
          </p>
          <div style="display:inline-flex;align-items:center;gap:7px;padding:9px 18px;
               background:#eff6ff;border-radius:9px;border:1px solid #bfdbfe">
            <span style="font-size:13px;color:#1e40af;font-weight:600">📋 Pending recruiter review</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    total_q = len(st.session_state.question_history)
    m1, m2, m3 = st.columns(3)
    m1.metric("Questions answered", str(total_q))
    m2.metric("Interview status",   "Submitted")
    m3.metric("Results",            "Saved ✓")
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;
         padding:18px 20px;margin-bottom:4px">
      <div style="font-size:13px;font-weight:600;color:#1e40af;margin-bottom:5px">What happens next?</div>
      <div style="font-size:13px;color:#3b5bdb;line-height:1.7">
        The recruiter will review your engagement analysis, behavioral scores, and answers.
        You'll be contacted about next steps via your registered details.
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.markdown('<div style="margin-bottom:8px"><div style="font-size:14px;font-weight:600;color:var(--text)">Practice again?</div><div style="font-size:12px;color:var(--muted);margin-top:2px">Start fresh with a different resume or JD.</div></div>', unsafe_allow_html=True)
        if st.button("Start New Interview", use_container_width=True): _new_interview()
    with c2:
        st.markdown('<div style="margin-bottom:8px"><div style="font-size:14px;font-weight:600;color:var(--text)">All done?</div><div style="font-size:12px;color:var(--muted);margin-top:2px">Your results are saved. Safe to log out.</div></div>', unsafe_allow_html=True)
        if st.button("Logout →", type="primary", use_container_width=True, key="rep_logout"): _logout()


# ── ALL CAMERA PHASES ─────────────────────────────────────────────────────
else:
    QUESTIONS   = st.session_state.get("questions", [])
    is_rec      = (phase == "recording")
    cand_name   = st.session_state.auth_display_name or "Candidate"

    # Two-column layout
    main_col, cam_col = st.columns([2.5, 1], gap="large")

    # ══════════════════════════════════════════════════════════════════════
    # CAMERA COLUMN  —  professional "studio monitor" design
    # ══════════════════════════════════════════════════════════════════════
    with cam_col:

        # ── Top chrome bar ────────────────────────────────────────────
        rec_badge = (
            '<div style="display:flex;align-items:center;gap:4px;'
            'background:rgba(239,68,68,0.82);border-radius:20px;padding:3px 9px">'
            '<div style="width:5px;height:5px;border-radius:50%;background:#fff;'
            'animation:rec-blink 1.1s ease-in-out infinite"></div>'
            '<span style="font-size:8px;font-weight:700;color:#fff;letter-spacing:1px;'
            'text-transform:uppercase;font-family:var(--mono)">REC</span></div>'
            if is_rec else
            '<div style="display:flex;align-items:center;gap:4px;'
            'background:rgba(34,197,94,0.75);border-radius:20px;padding:3px 9px">'
            '<div style="width:5px;height:5px;border-radius:50%;background:#fff"></div>'
            '<span style="font-size:8px;font-weight:700;color:#fff;letter-spacing:1px;'
            'text-transform:uppercase;font-family:var(--mono)">LIVE</span></div>'
        )

        st.markdown(f"""
        <div style="background:var(--cam-bg);border:1px solid var(--cam-border);
             border-radius:16px 16px 0 0;padding:9px 14px;
             display:flex;align-items:center;justify-content:space-between">
          <div style="display:flex;gap:5px;align-items:center">
            <div style="width:9px;height:9px;border-radius:50%;background:#ff5f57"></div>
            <div style="width:9px;height:9px;border-radius:50%;background:#febc2e"></div>
            <div style="width:9px;height:9px;border-radius:50%;background:#28c840"></div>
          </div>
          <div style="font-size:8.5px;font-weight:600;color:rgba(255,255,255,0.28);
               letter-spacing:1.5px;text-transform:uppercase;font-family:var(--mono)">CAMERA</div>
          {rec_badge}
        </div>
        """, unsafe_allow_html=True)

        # ── Video + dark wrapper ──────────────────────────────────────
        st.markdown("""
        <div style="background:#000;border-left:1px solid var(--cam-border);
             border-right:1px solid var(--cam-border);">
        """, unsafe_allow_html=True)

        ctx = webrtc_streamer(
            key="engagement",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory=EngagementProcessor,
            media_stream_constraints={"video": True, "audio": False},
            async_processing=True,
        )
        stream_ok = ctx.state.playing and ctx.video_processor is not None

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Name plate ────────────────────────────────────────────────
        status_dot_color = "#ef4444" if is_rec else "#22c55e"
        status_text      = "● RECORDING" if is_rec else "● STANDBY"
        st.markdown(f"""
        <div style="background:#0f0f1c;border-left:1px solid var(--cam-border);
             border-right:1px solid var(--cam-border);
             padding:8px 12px;display:flex;align-items:center;justify-content:space-between">
          <div style="font-size:11px;font-weight:600;color:rgba(255,255,255,0.72)">
            👤 {cand_name}</div>
          <div style="font-size:8.5px;font-weight:600;color:{status_dot_color};
               font-family:var(--mono);letter-spacing:0.5px">{status_text}</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Metrics panel ─────────────────────────────────────────────
        if stream_ok:
            try:
                _eng = ctx.video_processor.get_avg_score()
                _abs = ctx.video_processor.get_absence_ratio()
                _emo = ctx.video_processor.get_emotion_summary()
            except:
                _eng, _abs, _emo = 0.0, 0.0, {"dominant": "–"}

            eng_c = _metric_color(_eng, 7, 4)
            abs_c = _metric_color(_abs, 0.15, 0.30, invert=True)
            pres  = (1 - _abs) * 100
            dom   = str(_emo.get("dominant", "–")).capitalize() if _emo else "–"

            st.markdown(f"""
            <div style="background:var(--cam-bg);border:1px solid var(--cam-border);
                 border-top:none;border-radius:0 0 16px 16px;overflow:hidden">

              <div style="display:grid;grid-template-columns:1fr 1fr;
                   gap:1px;background:var(--cam-border)">
                <div style="background:#10101f;padding:12px 10px;text-align:center">
                  <div style="font-size:20px;font-weight:700;color:{eng_c};
                       font-family:var(--mono);line-height:1">{_eng:.1f}</div>
                  <div style="font-size:8px;font-weight:600;color:rgba(255,255,255,0.32);
                       letter-spacing:1px;text-transform:uppercase;margin-top:5px">Engagement</div>
                </div>
                <div style="background:#10101f;padding:12px 10px;text-align:center">
                  <div style="font-size:20px;font-weight:700;color:{abs_c};
                       font-family:var(--mono);line-height:1">{pres:.0f}%</div>
                  <div style="font-size:8px;font-weight:600;color:rgba(255,255,255,0.32);
                       letter-spacing:1px;text-transform:uppercase;margin-top:5px">Presence</div>
                </div>
              </div>

              <div style="background:#0d0d1a;padding:9px 14px;
                   display:flex;align-items:center;justify-content:space-between;
                   border-top:1px solid var(--cam-border)">
                <div style="font-size:8px;font-weight:600;color:rgba(255,255,255,0.28);
                     letter-spacing:1px;text-transform:uppercase;font-family:var(--mono)">
                  EMOTION</div>
                <div style="font-size:12px;font-weight:600;color:rgba(255,255,255,0.78)">
                  {dom}</div>
              </div>

            </div>
            """, unsafe_allow_html=True)

            if _abs > 0.30:
                st.error("⚠️ Stay in frame!")
            elif _abs > 0.15:
                st.warning("👁 Look at camera")

        else:
            st.markdown("""
            <div style="background:var(--cam-bg);border:1px solid var(--cam-border);
                 border-top:none;border-radius:0 0 16px 16px;
                 padding:22px 14px;text-align:center">
              <div style="font-size:26px;margin-bottom:10px;opacity:0.35">📷</div>
              <div style="font-size:11px;color:rgba(255,255,255,0.32);line-height:1.7">
                Click <span style="color:rgba(110,100,255,0.9);font-weight:600">START</span>
                above<br>to enable camera
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # MAIN CONTENT COLUMN
    # ══════════════════════════════════════════════════════════════════════
    with main_col:

        # ── CAMERA SETUP ──────────────────────────────────────────────
        if phase == "camera_setup":
            render_stepper(1)
            page_title("Camera Check", "Allow camera access — make sure you're well lit and centred.")
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

            if stream_ok:
                c1, c2, c3 = st.columns(3)
                c1.success("✓ Camera on")
                c2.success("✓ Face detected")
                c3.info("ℹ  Mic separate")
                st.markdown("""
                <div style="margin-top:16px;padding:16px 20px;background:#effaf4;
                     border-radius:12px;border:1px solid #b6f0cc">
                  <div style="font-size:14px;font-weight:600;color:#166534">
                    Everything looks good — launching the interview…</div>
                </div>""", unsafe_allow_html=True)
                time.sleep(1.5)
                go_to("prep")
            else:
                st.markdown("""
                <div class="ps-card">
                  <div style="font-size:15px;font-weight:600;color:var(--text);margin-bottom:8px">
                    How to enable your camera</div>
                  <div style="font-size:13px;color:var(--muted);line-height:1.7">
                    Click the <strong>START</strong> button in the camera panel on the right.
                    When your browser asks for permission, click <strong>Allow</strong>.<br><br>
                    Make sure you're in a <strong>well-lit spot</strong> with your face clearly visible.
                  </div>
                </div>""", unsafe_allow_html=True)
                tc1, tc2, tc3 = st.columns(3)
                for col, icon, title, tip in [
                    (tc1, "💡", "Lighting",    "Face the light source, avoid backlight"),
                    (tc2, "👁", "Framing",     "Keep face centred, shoulders visible"),
                    (tc3, "🔇", "Quiet space", "Minimise background noise"),
                ]:
                    with col:
                        st.markdown(f"""
                        <div class="ps-card" style="text-align:center;padding:18px 14px">
                          <div style="font-size:22px;margin-bottom:8px">{icon}</div>
                          <div style="font-size:13px;font-weight:600;color:var(--text)">{title}</div>
                          <div style="font-size:11px;color:var(--muted);margin-top:4px;line-height:1.5">{tip}</div>
                        </div>""", unsafe_allow_html=True)
                time.sleep(1)
                st.rerun()

        # ── PREP ──────────────────────────────────────────────────────
        elif phase == "prep":
            render_stepper(2)
            q     = QUESTIONS[st.session_state.q_index]
            q_num = st.session_state.q_index + 1
            q_tot = len(QUESTIONS)

            q_label(q_num, q_tot)
            st.progress(st.session_state.q_index / q_tot)
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="ps-card" style="border-left:3px solid var(--indigo)">
              <div style="font-size:10px;font-weight:700;color:var(--indigo);
                   text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">
                Read the question</div>
              <div style="font-size:17px;font-weight:600;color:var(--text);line-height:1.65">{q}</div>
            </div>""", unsafe_allow_html=True)

            st.session_state.cur_engagement = None
            st.session_state.cur_absence    = None

            if not st.session_state.question_spoken:
                speak_question(q)
                st.session_state.question_spoken = True
                st.session_state.prep_start      = time.time()
                if stream_ok:
                    ctx.video_processor.snapshot_and_reset()

            elapsed   = int(time.time() - st.session_state.prep_start)
            remaining = PREP_TIME - elapsed

            if remaining > 0:
                if stream_ok:
                    ctx.video_processor.set_countdown(remaining)
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:16px;padding:16px 20px;
                     background:var(--bg);border-radius:12px;border:1px solid var(--border)">
                  <div style="text-align:center;min-width:64px;
                       padding:10px 12px;background:var(--surface);border-radius:10px;
                       border:1px solid var(--border)">
                    <div style="font-size:30px;font-weight:700;color:var(--text);
                         line-height:1;font-family:var(--mono)">{remaining}</div>
                    <div style="font-size:10px;color:var(--muted);font-weight:600;margin-top:2px">sec</div>
                  </div>
                  <div>
                    <div style="font-size:13px;font-weight:600;color:var(--text)">Prepare your answer</div>
                    <div style="font-size:12px;color:var(--muted);margin-top:3px">
                      Recording starts automatically when the timer reaches zero.</div>
                  </div>
                </div>""", unsafe_allow_html=True)
                st.progress((PREP_TIME - remaining) / PREP_TIME)
                time.sleep(1)
                st.rerun()
            else:
                if stream_ok:
                    ctx.video_processor.set_countdown(None)
                st.session_state.record_container = {
                    "text": "", "done": False, "wav_path": None, "duration": 60}
                st.session_state.record_start = time.time()
                if stream_ok:
                    ctx.video_processor.snapshot_and_reset()
                record_answer_background(st.session_state.record_container, RECORD_TIME)
                go_to("recording")

        # ── RECORDING ─────────────────────────────────────────────────
        elif phase == "recording":
            render_stepper(2)
            q     = QUESTIONS[st.session_state.q_index]
            q_num = st.session_state.q_index + 1
            q_tot = len(QUESTIONS)

            q_label(q_num, q_tot)
            st.progress(st.session_state.q_index / q_tot)
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="ps-card" style="border-left:3px solid var(--red)">
              <div style="display:flex;align-items:center;gap:7px;margin-bottom:10px">
                <div style="width:8px;height:8px;border-radius:50%;background:var(--red);
                     animation:ps-blink 1.1s ease-in-out infinite"></div>
                <div style="font-size:10px;font-weight:700;color:var(--red);
                     text-transform:uppercase;letter-spacing:0.8px">Recording in progress</div>
              </div>
              <div style="font-size:17px;font-weight:600;color:var(--text);line-height:1.65">{q}</div>
            </div>""", unsafe_allow_html=True)

            elapsed   = int(time.time() - st.session_state.record_start)
            remaining = RECORD_TIME - elapsed
            if stream_ok:
                ctx.video_processor.set_countdown(None)

            if remaining > 0:
                t_col, s_col = st.columns([1, 2], gap="medium")
                with t_col:
                    pct = remaining / RECORD_TIME
                    clr = "var(--red)" if pct < 0.25 else ("var(--amber)" if pct < 0.5 else "var(--indigo)")
                    st.markdown(f"""
                    <div style="text-align:center;padding:20px 14px;background:#fef2f2;
                         border-radius:12px;border:1px solid #fecaca">
                      <div style="font-size:34px;font-weight:700;color:{clr};
                           letter-spacing:-1.5px;line-height:1;font-family:var(--mono)">{remaining}</div>
                      <div style="font-size:11px;color:var(--red);font-weight:600;margin-top:4px">
                        sec remaining</div>
                    </div>""", unsafe_allow_html=True)
                with s_col:
                    st.markdown("""
                    <div class="ps-inset" style="margin-bottom:0">
                      <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:6px">
                        Speak your answer clearly</div>
                      <div style="font-size:12px;color:var(--muted);line-height:1.65">
                        Use the <strong style="color:var(--indigo)">STAR</strong> method —
                        <strong>S</strong>ituation · <strong>T</strong>ask ·
                        <strong>A</strong>ction · <strong>R</strong>esult
                      </div>
                    </div>""", unsafe_allow_html=True)
                st.progress((RECORD_TIME - remaining) / RECORD_TIME)
                time.sleep(1)
                st.rerun()
            else:
                if stream_ok:
                    score, absent, fem = ctx.video_processor.snapshot_and_reset()
                    if score == 0.0: score = 5.0
                else:
                    score, absent, fem = 5.0, 0.0, {"dominant": "neutral", "breakdown": {}}
                st.session_state.cur_engagement     = score
                st.session_state.cur_absence        = absent
                st.session_state.cur_facial_emotion = fem
                go_to("processing")

        # ── PROCESSING ────────────────────────────────────────────────
        elif phase == "processing":
            render_stepper(2)
            q = QUESTIONS[st.session_state.q_index]
            st.markdown(f"""
            <div class="ps-card">
              <div style="font-size:13px;color:var(--muted);line-height:1.6">{q}</div>
            </div>
            <div style="text-align:center;padding:28px;background:var(--surface);
                 border-radius:14px;border:1px solid var(--border);box-shadow:var(--shadow)">
              <div style="font-size:15px;font-weight:600;color:var(--text);margin-bottom:6px">
                Transcribing your answer…</div>
              <div style="font-size:13px;color:var(--muted)">Using Whisper AI — a few seconds.</div>
            </div>""", unsafe_allow_html=True)
            if not st.session_state.record_container["done"]:
                time.sleep(1)
                st.rerun()
            else:
                st.session_state.answer_input = st.session_state.record_container["text"]
                go_to("transcript")

        # ── TRANSCRIPT + SUBMIT ───────────────────────────────────────
        elif phase == "transcript":
            render_stepper(2)
            q       = QUESTIONS[st.session_state.q_index]
            ans     = st.session_state.answer_input
            eng     = st.session_state.cur_engagement
            abr     = st.session_state.cur_absence
            q_num   = st.session_state.q_index + 1
            q_tot   = len(QUESTIONS)
            is_last = q_num == q_tot

            q_label(q_num, q_tot, "Review")
            st.progress(q_num / q_tot)
            st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="ps-card">
              <div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;
                   letter-spacing:0.8px;margin-bottom:8px">Question</div>
              <div style="font-size:16px;font-weight:600;color:var(--text);line-height:1.65">{q}</div>
            </div>""", unsafe_allow_html=True)

            has_ans  = bool(ans and ans.strip())
            t_bg     = "#effaf4" if has_ans else "#fef2f2"
            t_border = "#b6f0cc" if has_ans else "#fecaca"
            t_text   = "#1a3a20" if has_ans else "#7f1d1d"
            t_label  = "#16a34a" if has_ans else "#dc2626"
            t_body   = ans if has_ans else "No speech detected. Please use the Re-record button below."

            st.markdown(f"""
            <div style="background:{t_bg};border:1px solid {t_border};border-radius:12px;
                 padding:16px 20px;margin-bottom:16px">
              <div style="font-size:10px;font-weight:700;color:{t_label};
                   text-transform:uppercase;letter-spacing:0.8px;margin-bottom:9px">
                Your transcript</div>
              <div style="font-size:14px;color:{t_text};line-height:1.75">{t_body}</div>
            </div>""", unsafe_allow_html=True)

            if eng is not None and abr is not None:
                m1, m2 = st.columns(2)
                eng_icon = "🟢" if eng >= 7 else ("🟡" if eng >= 4 else "🔴")
                abs_icon = "🟢" if abr <= 0.15 else ("🟡" if abr <= 0.30 else "🔴")
                m1.metric(f"{eng_icon}  Engagement", f"{eng:.1f} / 10")
                m2.metric(f"{abs_icon}  Face presence", f"{(1-abr)*100:.0f}%")
                if abr > 0.30:
                    st.error("⚠️ Low face presence — the recruiter will see this flag.")

            st.markdown("<hr>", unsafe_allow_html=True)
            btn_col1, btn_col2 = st.columns([1, 1.6], gap="medium")

            with btn_col1:
                if not st.session_state.retry_used:
                    if st.button("🔁  Re-record", use_container_width=True):
                        st.session_state.retry_used       = True
                        st.session_state.record_container = {
                            "text": "", "done": False, "wav_path": None, "duration": 60}
                        st.session_state.record_start     = time.time()
                        if stream_ok:
                            ctx.video_processor.snapshot_and_reset()
                        record_answer_background(st.session_state.record_container, RECORD_TIME)
                        go_to("recording")
                else:
                    st.markdown(
                        '<div style="font-size:12px;color:#aaaabc;padding-top:12px">'
                        'Re-record already used</div>', unsafe_allow_html=True)

            with btn_col2:
                lbl = ("Submit & Finish Interview →" if is_last
                       else f"Submit & Next Question ({q_num}/{q_tot}) →")
                if st.button(lbl, type="primary", use_container_width=True):
                    try:
                        er = requests.post("http://127.0.0.1:8000/evaluate_answer",
                            json={"question": q, "answer": ans,
                                  "jd_text": st.session_state.get("jd_text","")},
                            timeout=30).json()
                        cog     = er.get("cognitive_score", 5.0)
                        verdict = er.get("recruiter_verdict", "Borderline")
                        dims    = er.get("dimension_scores", {})
                    except Exception as _e:
                        st.error(f"Evaluation error: {_e}")
                        cog, verdict, dims = 5.0, "Borderline", {}

                    try:
                        _wav = st.session_state.record_container.get("wav_path")
                        _dur = st.session_state.record_container.get("duration", 60)
                        _ej  = requests.post("http://127.0.0.1:8002/predict_detail",
                            json={"text": ans, "wav_path": _wav, "duration_seconds": _dur},
                            timeout=30).json()
                        emo  = float(_ej.get("emotion_score", 5.0))
                        st.session_state.speech_breakdowns.append(_ej)
                        if _wav:
                            import os as _os
                            try: _os.unlink(_wav)
                            except: pass
                    except Exception as _e:
                        st.warning(f"Speech scoring unavailable: {_e}")
                        emo = 5.0
                        st.session_state.speech_breakdowns.append({})

                    st.session_state.cognitive_scores.append(cog)
                    st.session_state.emotion_scores.append(emo)
                    st.session_state.engagement_scores.append(eng if eng is not None else 5.0)
                    st.session_state.absence_ratios.append(abr if abr is not None else 0.0)
                    st.session_state.low_presence_flags.append((abr or 0.0) > 0.30)
                    st.session_state.question_history.append(q)
                    st.session_state.answer_history.append(ans)
                    st.session_state.recruiter_verdicts.append(verdict)
                    st.session_state.dimension_scores.append(dims)
                    st.session_state.facial_emotions.append(
                        st.session_state.get("cur_facial_emotion",
                                             {"dominant": "neutral", "breakdown": {}}))

                    st.session_state.q_index        += 1
                    st.session_state.question_spoken = False
                    st.session_state.retry_used      = False
                    st.session_state.cur_engagement  = None
                    st.session_state.cur_absence     = None

                    if st.session_state.q_index >= len(QUESTIONS):
                        go_to("report")
                    else:
                        go_to("prep")