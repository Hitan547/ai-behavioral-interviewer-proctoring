"""
app.py — PsySense AI Mock Interview (v4 — Professional Camera UI)

UI changes vs v3:
- Camera panel styled like HireVue/Karat: dark "monitor" chrome, name plate,
  animated REC indicator, live metric chips inside the camera frame
- Camera column uses dark #0d0d14 bg so video feels immersive / professional
- Engagement/Presence/Delivery shown as styled chips INSIDE the camera panel
- Global design tokens via CSS :root variables — consistent everywhere
- JetBrains Mono used for all numeric readouts (timers, metrics)
- STOP button fully suppressed (CSS + JS)
- Phase routing: correct if/elif/else (no start-screen bleed)

Logic: UNCHANGED from v3.
"""

import streamlit as st
import requests
import time
import threading as _threading
import os
import html
import json
import numpy as np
from config import (
    ANSWER_SERVICE_URL, FUSION_SERVICE_URL,
    EMOTION_SERVICE_URL, INSIGHT_SERVICE_URL,
    N8N_RESULT_WEBHOOK
)
from audio_capture_robust import (
    save_webrtc_frames_to_wav as save_audio_frames_to_wav,
    transcribe_wav,
    get_webrtc_config_for_saas,
)
from database import init_db, verify_login, register_student, save_session, get_all_sessions, update_interview_status
from recruiter_dashboard import show_recruiter_dashboard
from voice_question import speak_question
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, AudioProcessorBase, WebRtcMode
from engagement_realtime import EngagementDetector
import av

groq_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")

init_db()

st.set_page_config(
    page_title="PsySense — AI Interview",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",

)

if not groq_key:
    st.error("⚠️ GROQ_API_KEY is not set. Transcription will fail. Add it to your .env file.")
    st.stop()

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

/* Keep WebRTC controls visible for compatibility across streamlit-webrtc versions. */

/* ── App bg ── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main { background: var(--bg) !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
  min-width: 260px !important; max-width: 260px !important;
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
""", unsafe_allow_html=True)

# Try to release stale media tracks on each render before WebRTC initializes.
st.markdown("""
<script>
(function releaseCameraTracks() {
    try {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: true, audio: true })
                .then(function(stream) {
                    stream.getTracks().forEach(function(track) { track.stop(); });
                })
                .catch(function() {});
        }

        document.querySelectorAll("video").forEach(function(video) {
            if (video && video.srcObject && video.srcObject.getTracks) {
                video.srcObject.getTracks().forEach(function(track) { track.stop(); });
                video.srcObject = null;
            }
        });
    } catch (e) {}
})();
</script>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# ANTI-CHEATING PROCTORING — Client-Side (from proctoring_client module)
# ══════════════════════════════════════════════════════════════════════════
from proctoring_client import (
    inject_proctoring_ui,
    inject_proctoring_js,
    render_proctoring_chips,
    sync_proctoring_state_from_query_params,
    build_proctoring_summary,
)

inject_proctoring_ui()   # CSS + HTML overlays
inject_proctoring_js()   # JavaScript event listeners
sync_proctoring_state_from_query_params()


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
        return self.detector.snapshot_and_reset()


class AudioCaptureProcessor(AudioProcessorBase):
    """Captures raw audio frames from browser mic into a thread-safe buffer."""

    def __init__(self):
        self._frames = []
        self._lock = _threading.Lock()
        self._capturing = False
        self._recv_count = 0
        # Browser usually provides 48kHz, but detect from frame metadata to avoid mismatch.
        self.sample_rate = 48000

    def start(self):
        print("[AudioCaptureProcessor] START called")
        with self._lock:
            self._frames = []
            self._capturing = True
            self._recv_count = 0
        print("[AudioCaptureProcessor] Capturing enabled")

    def stop_and_get(self):
        with self._lock:
            buffered = len(self._frames)
        print(f"[AudioCaptureProcessor] STOP called - had {buffered} buffered frames")
        with self._lock:
            self._capturing = False
            frames = list(self._frames)
            self._frames = []
            return frames

    def pop_frames(self):
        """Read and clear buffered frames while capture continues."""
        with self._lock:
            frames = list(self._frames)
            self._frames = []
            return frames

    def drain(self):
        """Clear buffer without stopping — use between prep and recording."""
        with self._lock:
            self._frames = []

    def _frame_to_mono(self, frame):
        """Convert av.AudioFrame to float32 mono in [-1, 1]."""
        arr = frame.to_ndarray()
        if arr is None:
            return np.array([], dtype=np.float32)
        arr = np.asarray(arr)
        if arr.size == 0:
            return np.array([], dtype=np.float32)
        fmt = getattr(frame.format, "name", "unknown")
        frame_samples = getattr(frame, "samples", None)

        def _finalize(mono_arr, scale=None):
            out = np.asarray(mono_arr).reshape(-1).astype(np.float32)
            if scale is not None:
                out = out / float(scale)
            if isinstance(frame_samples, int) and frame_samples > 0:
                if out.size > frame_samples:
                    out = out[:frame_samples]
                elif 0 < out.size < frame_samples:
                    out = np.pad(out, (0, frame_samples - out.size), mode="constant")
            return np.clip(out, -1.0, 1.0)

        if self._recv_count <= 5:
            print(
                f"[Audio] format={fmt}, shape={arr.shape}, dtype={arr.dtype}, "
                f"sample_rate={getattr(frame, 'sample_rate', 'n/a')}, "
                f"samples={getattr(frame, 'samples', 'n/a')}"
            )

        if fmt == "fltp":
            mono = arr.mean(axis=0) if arr.ndim == 2 else arr.reshape(-1)
            return _finalize(mono)

        if fmt == "s16p":
            # Planar int16: (channels, samples)
            mono = arr.mean(axis=0) if arr.ndim == 2 else arr.reshape(-1)
            return _finalize(mono, scale=32768.0)

        if fmt == "s16":
            # Packed int16 often arrives as shape (1, channels*samples).
            # CRITICAL: Detect actual channel count from frame.samples.
            # e.g. shape=(1,1920) with samples=960 means 2ch stereo packed.
            if arr.ndim == 2 and arr.shape[0] == 1:
                packed = arr.reshape(-1).astype(np.float32)

                # Detect channel count from frame metadata
                ch_count = 1
                if isinstance(frame_samples, int) and frame_samples > 0:
                    detected_ch = packed.size // frame_samples
                    if detected_ch in (1, 2, 4, 6, 8):
                        ch_count = detected_ch

                # Fallback: try layout metadata
                if ch_count == 1:
                    try:
                        layout = getattr(frame, "layout", None)
                        if layout is not None:
                            ch_count = int(getattr(layout, "channels", 1) or 1)
                    except Exception:
                        pass

                if ch_count > 1 and packed.size >= ch_count:
                    usable = (packed.size // ch_count) * ch_count
                    if usable > 0:
                        packed = packed[:usable].reshape(-1, ch_count).mean(axis=1)
                        if self._recv_count <= 5:
                            print(f"[Audio] Deinterleaved {ch_count}ch -> mono ({len(packed)} samples)")
                return _finalize(packed, scale=32768.0)

            mono = arr.mean(axis=0) if arr.ndim == 2 else arr.reshape(-1)
            return _finalize(mono, scale=32768.0)

        if arr.ndim == 2:
            axis = 0 if arr.shape[0] <= 4 else 1
            arr = arr.mean(axis=axis)
        arr = arr.reshape(-1).astype(np.float32)
        peak = float(np.abs(arr).max()) if arr.size else 0.0
        if peak > 1.0:
            arr = arr / peak
        return _finalize(arr)

    def _silent_frame_from(self, frame):
        """Create a silent frame matching input metadata to avoid sendback echo."""
        try:
            arr = frame.to_ndarray()
            silent = av.AudioFrame.from_ndarray(
                np.zeros_like(arr),
                format=frame.format.name,
                layout=frame.layout.name,
            )
            silent.sample_rate = frame.sample_rate
            silent.pts = frame.pts
            if hasattr(frame, "time_base"):
                silent.time_base = frame.time_base
            return silent
        except Exception as e:
            print(f"[AudioCaptureProcessor] ERROR building silent frame: {e}")
            return frame

    def recv(self, frame):
        self._recv_count += 1
        try:
            frame_sr = getattr(frame, "sample_rate", None)
            if frame_sr:
                self.sample_rate = int(frame_sr)
        except Exception:
            pass

        if self._recv_count % 10 == 0 or self._recv_count <= 3:
            status = "ON" if self._capturing else "OFF"
            with self._lock:
                buf_size = len(self._frames)
            print(
                f"[AudioCaptureProcessor] recv() call #{self._recv_count} - "
                f"capturing={status}, buffer_size={buf_size}"
            )

        if self._capturing:
            try:
                mono = self._frame_to_mono(frame)
                if mono is not None and len(mono) > 0:
                    with self._lock:
                        self._frames.append(mono)
                        if self._recv_count <= 3:
                            print(
                                f"  -> Added frame: {len(mono)} samples, "
                                f"buffer now has {len(self._frames)} frames"
                            )
            except Exception as e:
                print(f"[AudioCaptureProcessor] ERROR in recv: {e}")

        # Always send back silence so audio track is consumed by WebRTC
        # without creating speaker echo/loopback in the browser.
        return self._silent_frame_from(frame)

    async def recv_queued(self, frames):
        # Keep compatibility path for streamlit-webrtc async queue mode.
        output_frames = []
        converted = []

        for frame in frames:
            self._recv_count += 1
            try:
                frame_sr = getattr(frame, "sample_rate", None)
                if frame_sr:
                    self.sample_rate = int(frame_sr)
            except Exception:
                pass

            if self._recv_count % 50 == 0:
                status = "ON" if self._capturing else "OFF"
                with self._lock:
                    buf_size = len(self._frames)
                print(
                    f"[AudioCaptureProcessor] recv_queued total_calls={self._recv_count} "
                    f"capturing={status}, batch_size={len(frames)}, buffer_size={buf_size}"
                )

            if self._capturing:
                try:
                    mono = self._frame_to_mono(frame)
                    if mono is not None and len(mono) > 0:
                        converted.append(mono)
                except Exception as e:
                    print(f"[AudioCaptureProcessor] ERROR in recv_queued: {e}")

            output_frames.append(self._silent_frame_from(frame))

        if converted:
            with self._lock:
                self._frames.extend(converted)

        return output_frames


if not st.session_state.get("_audio_diag_banner_printed", False):
    print(
        "[DEBUG] AudioCaptureProcessor diagnostic logging enabled. "
        "Watch terminal for START and recv() events during recording."
    )
    st.session_state["_audio_diag_banner_printed"] = True


PREP_TIME   = 15
RECORD_TIME = 60
AUDIO_REARM_DELAY_SEC = 2.5

# ══════════════════════════════════════════════════════════════════════════
# SESSION DEFAULTS
# ══════════════════════════════════════════════════════════════════════════
_D = {
    "logged_in": False, "user_role": None,
    "auth_username": "", "auth_display_name": "",
    "org_id": None,
    "recruiter_detail_id": None, "recruiter_view_users": False,
    "phase": "start", "q_index": 0,
    "camera_ready_confirmed": False,
    "candidate_name": "", "questions": [], "resume_text": "", "jd_text": "",
    "question_spoken": False, "session_saved": False,
    "saved_session_id": None, "webhook_sent": False,
    "prep_start": None, "record_start": None, "retry_used": False,
    "record_container": {
        "text": "", "done": False, "wav_path": None, "duration": 60, "error": None
    },
    "audio_capture_debug": "",
    "audio_capture_started": False,
    "audio_capture_processor_id": None,
    "answer_input": "",
    "fullscreen_gate_shown": False,
    "cognitive_scores": [], "emotion_scores": [], "engagement_scores": [],
    "jd_id": None,
    "audio_frames": [],   # collects browser audio frames during recording 
    "absence_ratios": [], "low_presence_flags": [],
    "question_history": [], "answer_history": [],
    "recruiter_verdicts": [], "dimension_scores": [],
    "cur_engagement": None, "cur_absence": None,
    "cur_facial_emotion": {"dominant": "neutral", "breakdown": {}},
    "speech_breakdowns": [], "facial_emotions": [],
    "resume_vocab": {},  # technical vocabulary extracted from resume for Whisper
    "question_keywords": [],  # per-question keywords for accurate transcription
    "webrtc_reset_nonce": 0,
    "_last_webrtc_diag": None,
    "_last_webrtc_ctx_id": None,
    # Anti-cheating proctoring
    "proctoring_tab_switches": 0,
    "proctoring_paste_attempts": 0,
    "proctoring_fullscreen_exits": 0,
    "proctoring_multi_face_total": 0,
    "proctoring_screen_count": 1,
    "proctoring_devtools_attempts": 0,
    "proctoring_events": [],          # detailed event log
    "proctoring_warning_level": "none",  # none/yellow/orange/red
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
            ["logged_in", "user_role", "auth_username", "auth_display_name", "org_id", "user_email"]
            if k in st.session_state}
    st.session_state.clear()
    for k, v in _D.items():
        st.session_state[k] = v
    st.session_state.update(keep)
    st.rerun()


def _load_invited_candidate_context() -> bool:
    """Load saved recruiter-provided resume/JD for invited candidates."""
    if st.session_state.get("user_role") != "student":
        return False
    if st.session_state.get("invited_candidate_loaded") and st.session_state.get("invited_candidate"):
        return bool(st.session_state.get("invited_candidate"))

    st.session_state.invited_candidate_loaded = True
    try:
        from database import get_profile_for_candidate, get_job_posting_by_id

        profile = get_profile_for_candidate(
            st.session_state.auth_username,
            st.session_state.get("user_email", ""),
        )
        if not profile or not (profile.resume_text or "").strip():
            st.session_state.invited_candidate = False
            return False

        posting = get_job_posting_by_id(profile.jd_id) if profile.jd_id else None
        st.session_state.invited_candidate = True
        st.session_state.candidate_name = profile.name or st.session_state.auth_display_name
        st.session_state.resume_text = profile.resume_text or ""
        st.session_state.jd_id = profile.jd_id
        st.session_state.jd_text = posting.jd_text if posting else ""
        st.session_state.invited_job_title = posting.title if posting else "Interview"
        st.session_state.invited_deadline = (
            posting.deadline.strftime("%d %b %Y") if posting and posting.deadline else ""
        )
        st.session_state.invited_profile_id = profile.id
        st.session_state.prepared_questions = _safe_json_loads(
            getattr(profile, "questions_json", None), []
        )
        st.session_state.prepared_question_keywords = _safe_json_loads(
            getattr(profile, "keywords_json", None), []
        )
        st.session_state.prepared_vocab = _safe_json_loads(
            getattr(profile, "vocab_json", None), {}
        )
        return True
    except Exception as e:
        print(f"[candidate] Could not load invited context: {e}", flush=True)
        st.session_state.invited_candidate = False
        return False


def _safe_json_loads(raw_value, fallback):
    if not raw_value:
        return fallback
    try:
        parsed = json.loads(raw_value)
        return fallback if parsed is None else parsed
    except Exception:
        return fallback


def _build_transcription_vocab_for_question(question_index: int) -> dict:
    """Use per-question keywords first, then fall back to saved resume/JD vocab."""
    q_keywords = st.session_state.get("question_keywords", []) or []
    per_q_kw = q_keywords[question_index] if question_index < len(q_keywords) else []
    if per_q_kw:
        return {
            "acronyms": per_q_kw,
            "proper_nouns": [],
            "terms": [],
        }
    return st.session_state.get("resume_vocab") or {}


# ══════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    from saas.saas_auth import show_saas_login_signup
    show_saas_login_signup()
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# RECRUITER DASHBOARD (must run before candidate sidebar — avoids st.sidebar conflict)
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.user_role == "recruiter":
    show_recruiter_dashboard()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR — candidates only
# ══════════════════════════════════════════════════════════════════════════
st.markdown('<style>[data-testid="stSidebarNav"]{display:none!important}</style>',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f"""
    <div style="padding:6px 0 14px">
      <div style="font-size:10px;font-weight:700;color:#aaaabc;text-transform:uppercase;
           letter-spacing:0.8px;margin-bottom:8px">🎤 Candidate</div>
      <div style="font-size:15px;font-weight:700;color:var(--text);line-height:1.2">
        {st.session_state.auth_display_name}</div>
      <div style="font-size:12px;color:var(--muted);margin-top:3px">
        @{st.session_state.auth_username}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)
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
# PERSISTENT CAMERA RENDER (all phases)
# ══════════════════════════════════════════════════════════════════════════
is_rec = (phase == "recording")
cand_name = st.session_state.auth_display_name or "Candidate"

webrtc_config = get_webrtc_config_for_saas()
webrtc_config.pop("mode", None)
webrtc_config.pop("desired_playing_state", None)
webrtc_config.pop("async_processing", None)
webrtc_config.pop("sendback_audio", None)

if "rtc_configuration" not in webrtc_config:
    webrtc_config["rtc_configuration"] = {
        "iceServers": [
            {"urls": ["stun:stun.l.google.com:19302"]},
            {"urls": ["stun:stun1.l.google.com:19302"]},
        ],
    }

if "media_stream_constraints" not in webrtc_config:
    webrtc_config["media_stream_constraints"] = {
        "video": {
            "width": {"ideal": 640, "max": 1280},
            "height": {"ideal": 480, "max": 720},
            "frameRate": {"ideal": 15, "max": 30},
        },
        "audio": {
            "echoCancellation": True,
            "noiseSuppression": True,
            "autoGainControl": True,
        },
    }

webrtc_key = f"engagement-{st.session_state.webrtc_reset_nonce}"
main_col, cam_col = st.columns([2.5, 1], gap="large")

with cam_col:
    _hide_cam_ui = phase in ("start", "report")
    if _hide_cam_ui:
        st.markdown(
            '<div style="max-height:1px;overflow:hidden;opacity:0.01;pointer-events:none;">',
            unsafe_allow_html=True,
        )

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

    st.markdown("""
    <div style="background:#000;border-left:1px solid var(--cam-border);
         border-right:1px solid var(--cam-border);">
    """, unsafe_allow_html=True)

    ctx = webrtc_streamer(
        key=webrtc_key,
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=EngagementProcessor,
        audio_processor_factory=AudioCaptureProcessor,
        video_receiver_size=32,
        async_processing=True,
        sendback_audio=True,
        **webrtc_config,
    )

    st.markdown("""
    <script>
    (function patchWebRTCRetry() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
        if (window.__psysenseGumPatched) return;
        window.__psysenseGumPatched = true;

        const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = function(constraints) {
            let retryCount = 0;
            const maxRetries = 3;

            function attempt() {
                return original(constraints).catch(function(err) {
                    if (err && err.name === "AbortError" && retryCount < maxRetries) {
                        retryCount += 1;
                        return new Promise(function(resolve) {
                            setTimeout(resolve, 1500 * retryCount);
                        }).then(attempt);
                    }
                    throw err;
                });
            }

            return attempt();
        };
    })();
    </script>
    """, unsafe_allow_html=True)

    if not ctx.state.playing and not ctx.state.signalling and phase != "camera_setup":
        st.warning("Camera is not active. Return to Camera Check and click START.")

    ctx_obj_id = id(ctx)
    if st.session_state.get("_last_webrtc_ctx_id") != ctx_obj_id:
        print(f"[DEBUG] WebRTC context id changed: {ctx_obj_id} (key={webrtc_key})")
        st.session_state["_last_webrtc_ctx_id"] = ctx_obj_id

    _webrtc_diag = (
        bool(getattr(ctx.state, "playing", False)),
        bool(getattr(ctx.state, "signalling", False)),
        str(getattr(ctx.state, "ice_connection_state", "N/A")),
        bool(ctx.video_processor is not None),
        bool(ctx.audio_processor is not None),
        bool(getattr(ctx, "input_audio_track", None) is not None),
    )
    if st.session_state.get("_last_webrtc_diag") != _webrtc_diag:
        print("[DEBUG] webrtc_streamer state snapshot:")
        print(f"  key={webrtc_key}")
        print(f"  ctx.state.playing={ctx.state.playing}")
        print(f"  ctx.state.signalling={ctx.state.signalling}")
        print(f"  ctx.state.ice_connection_state={getattr(ctx.state, 'ice_connection_state', 'N/A')}")
        print(f"  ctx.video_processor={ctx.video_processor}")
        print(f"  ctx.audio_processor={ctx.audio_processor}")
        print(f"  input_audio_track={getattr(ctx, 'input_audio_track', None)}")
        print(f"  video_ready={_webrtc_diag[3]}, audio_proc={_webrtc_diag[4]}, input_audio={_webrtc_diag[5]}")
        st.session_state["_last_webrtc_diag"] = _webrtc_diag

    playing = bool(getattr(ctx.state, "playing", False))
    video_ready = bool(ctx.video_processor is not None)
    audio_processor_ready = bool(ctx.audio_processor is not None)
    audio_track_ready = bool(getattr(ctx, "input_audio_track", None) is not None)
    audio_ready = bool(audio_processor_ready and audio_track_ready)
    stream_ok = bool(playing and video_ready)
    stream_waiting = bool(playing and (not video_ready))

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="background:#0f0f1c;border:1px solid var(--cam-border);border-top:none;
         border-radius:0 0 16px 16px;padding:8px 12px;display:flex;
         align-items:center;justify-content:space-between">
      <div style="font-size:11px;font-weight:600;color:rgba(255,255,255,0.72)">👤 {cand_name}</div>
      <div style="font-size:8.5px;font-weight:600;color:{'#22c55e' if playing else '#ef4444'};
           font-family:var(--mono);letter-spacing:0.5px">
        {'● LIVE' if playing else '● OFFLINE'}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Proctoring status chips (shown during active interview) ──
    _interview_phases = ("prep", "recording", "processing", "transcript")
    if phase in _interview_phases:
        _tab_sw = st.session_state.get("proctoring_tab_switches", 0)
        _tab_cls = "ps-chip-ok" if _tab_sw == 0 else ("ps-chip-warn" if _tab_sw <= 2 else "ps-chip-bad")
        _mf = st.session_state.get("proctoring_multi_face_total", 0)
        _mf_cls = "ps-chip-ok" if _mf == 0 else "ps-chip-bad"
        st.markdown(f"""
        <div class="ps-proctor-chips">
          <span class="ps-proctor-chip {_tab_cls}">Tab: {_tab_sw}</span>
          <span class="ps-proctor-chip {_mf_cls}">Faces: {_mf}</span>
          <span class="ps-proctor-chip ps-chip-ok">Proctored</span>
        </div>
        """, unsafe_allow_html=True)

    if _hide_cam_ui:
        st.markdown("</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
# PHASE ROUTING  —  if / elif / else  (one branch per render pass)
# ══════════════════════════════════════════════════════════════════════════

# ── START ─────────────────────────────────────────────────────────────────
if phase == "start":
    with main_col:
        render_stepper(0)
        invited_candidate = _load_invited_candidate_context()
        if invited_candidate:
            page_title(
                f"Welcome, {st.session_state.auth_display_name}",
                "Your recruiter has prepared this interview from your resume and the job description.",
            )
            deadline = st.session_state.get("invited_deadline", "")
            deadline_html = f"<br><strong>Deadline:</strong> {html.escape(deadline)}" if deadline else ""
            job_title = html.escape(st.session_state.get("invited_job_title", "Interview"))
            st.markdown(f"""
            <div class="ps-card" style="border-left:3px solid var(--indigo)">
              <div style="font-size:10px;font-weight:700;color:var(--indigo);
                   text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px">
                Invited Interview</div>
              <div style="font-size:18px;font-weight:700;color:var(--text);margin-bottom:6px">
                {job_title}</div>
              <div style="font-size:13px;color:var(--muted);line-height:1.7">
                We will generate 5 personalized questions using the resume and JD already
                submitted by the recruiter.{deadline_html}
              </div>
            </div>
            """, unsafe_allow_html=True)

            m1, m2, m3 = st.columns(3)
            m1.metric("Questions", "5")
            m2.metric("Answer time", "60 sec each")
            m3.metric("Estimated time", "8-10 min")

            st.markdown("""
            <div style="background:#e0f2fe;border:1px solid #7dd3fc;border-radius:12px;
                 padding:14px 18px;margin-bottom:20px">
              <div style="font-size:13px;color:#0c4a6e;line-height:1.6">
                First, prepare the interview questions. Then you will complete a camera,
                microphone, and fullscreen check before the interview starts.
              </div>
            </div>""", unsafe_allow_html=True)

            _, cta, _ = st.columns([0.4, 1, 0.4])
            with cta:
                if st.button("Begin Setup", type="primary", use_container_width=True):
                    prepared = st.session_state.get("prepared_questions") or []
                    if len(prepared) >= 5:
                        qs = prepared[:5]
                        q_keywords = (st.session_state.get("prepared_question_keywords") or [])[:5]
                        vocab = st.session_state.get("prepared_vocab") or {}
                    else:
                        with st.spinner("Preparing your personalized questions..."):
                            from resume_parser import generate_questions_with_keywords
                            qs, q_keywords, vocab = generate_questions_with_keywords(
                                st.session_state.resume_text,
                                jd_text=st.session_state.get("jd_text", ""),
                            )
                            try:
                                from database import save_candidate_questions
                                save_candidate_questions(
                                    st.session_state.get("invited_profile_id"),
                                    qs,
                                    q_keywords,
                                    vocab,
                                )
                            except Exception as e:
                                print(f"[candidate] Could not save prepared questions: {e}", flush=True)
                    st.session_state.questions = qs
                    st.session_state.resume_vocab = vocab
                    st.session_state.question_keywords = q_keywords
                    st.success(f"✓ {len(qs)} questions ready")
                    time.sleep(0.8)
                    go_to("camera_setup")
            st.stop()
        page_title(f"Welcome, {st.session_state.auth_display_name} 👋",
                   "Upload your resume to get 5 personalised interview questions.")

        # Clear instruction banner
        st.markdown("""
        <div style="background:#e0f2fe;border:1px solid #7dd3fc;border-radius:12px;
             padding:14px 18px;margin-bottom:20px">
          <div style="font-size:13px;color:#0c4a6e;line-height:1.6">
            👉 <strong>First, click START in the camera panel on the right</strong> to enable your camera.
            Then upload your resume below.
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

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
                        from resume_parser import extract_resume_text, generate_questions_with_keywords
                        rt = extract_resume_text(tp)
                        qs, q_keywords, vocab = generate_questions_with_keywords(rt, jd_text=final_jd)
                    try: os.unlink(tp)
                    except: pass
                    st.session_state.questions    = qs
                    st.session_state.resume_text  = rt
                    st.session_state.resume_vocab = vocab
                    st.session_state.question_keywords = q_keywords
                    st.success(f"✓ {len(qs)} questions ready ({'resume + JD' if final_jd else 'resume only'})")
                    time.sleep(0.8)
                    go_to("camera_setup")


# ── REPORT ────────────────────────────────────────────────────────────────
elif phase == "report":
    with main_col:
        render_stepper(3)

        n       = max(len(st.session_state.cognitive_scores), 1)
        avg_cog = sum(st.session_state.cognitive_scores) / n
        avg_emo = sum(st.session_state.emotion_scores)   / max(len(st.session_state.emotion_scores), 1)
        avg_eng = sum(st.session_state.engagement_scores)/ max(len(st.session_state.engagement_scores), 1)

        try:
            fr = requests.post(f"{FUSION_SERVICE_URL}/fuse",
                json={"cognitive_score": avg_cog, "emotion_score": avg_emo,
                      "engagement_score": avg_eng}, timeout=10).json()
        except:
            fr = {"final_behavioral_score": round((0.70*avg_cog + 0.15*avg_emo + 0.15*avg_eng)*10, 1)}

        try:
            ir = requests.post(f"{INSIGHT_SERVICE_URL}/generate_insight",
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
                recruiter_verdicts=st.session_state.recruiter_verdicts,
                jd_id=st.session_state.get("jd_id"),
                proctoring_data=build_proctoring_summary())
            st.session_state.session_saved    = True
            st.session_state.saved_session_id = sid
            if st.session_state.get("org_id"):
                from saas.saas_db import increment_interview_count, reset_monthly_quota
                reset_monthly_quota(st.session_state.org_id)
                increment_interview_count(st.session_state.org_id)
            if not st.session_state.get("webhook_sent", False):
                try:
                    import datetime as _dt
                    from database import get_job_posting_by_id

                    jd_id      = st.session_state.get("jd_id")
                    should_fire = True
                    to_email    = None

                    if jd_id:
                        # JD-linked interview — only fire if score >= threshold
                        posting = get_job_posting_by_id(jd_id)
                        if posting:
                            should_fire = final_score >= posting.min_pass_score
                            to_email    = posting.recruiter_email

                    if should_fire:
                        payload = {
                            "candidate_name":    st.session_state.candidate_name,
                            "final_score":       final_score,
                            "cognitive_score":   round(avg_cog, 1),
                            "emotion_score":     round(avg_emo, 1),
                            "delivery_score":    round(avg_emo, 1),
                            "engagement_score":  round(avg_eng, 1),
                            "questions_answered": len(st.session_state.question_history),
                            "flagged":           final_score < 50,
                            "status":            "Passed" if jd_id else "Pending",
                            "interview_date":    _dt.datetime.now().strftime("%d %b %Y, %H:%M"),
                            "username":          st.session_state.auth_username,
                            "recruiter_email":   to_email,
                        }
                        requests.post(
                            N8N_RESULT_WEBHOOK,
                            json=payload, timeout=5
                        )
                        print(f"[n8n] ✅ Result email sent — score {final_score}", flush=True)
                    else:
                        print(f"[n8n] ⏭ Below threshold ({final_score}) — no email sent", flush=True)

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
        if st.session_state.get("invited_candidate"):
            _, done_col, _ = st.columns([0.5, 1, 0.5])
            with done_col:
                st.markdown(
                    '<div style="text-align:center;margin-bottom:10px">'
                    '<div style="font-size:14px;font-weight:600;color:var(--text)">All done</div>'
                    '<div style="font-size:12px;color:var(--muted);margin-top:2px">'
                    'Your interview has been submitted. You may safely log out.</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Logout ->", type="primary", use_container_width=True, key="rep_logout"):
                    _logout()
        else:
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                st.markdown('<div style="margin-bottom:8px"><div style="font-size:14px;font-weight:600;color:var(--text)">Practice again?</div><div style="font-size:12px;color:var(--muted);margin-top:2px">Start fresh with a different resume or JD.</div></div>', unsafe_allow_html=True)
                if st.button("Start New Interview", use_container_width=True): _new_interview()
            with c2:
                st.markdown('<div style="margin-bottom:8px"><div style="font-size:14px;font-weight:600;color:var(--text)">All done?</div><div style="font-size:12px;color:var(--muted);margin-top:2px">Your results are saved. Safe to log out.</div></div>', unsafe_allow_html=True)
                if st.button("Logout ->", type="primary", use_container_width=True, key="rep_logout"): _logout()


# ── ALL CAMERA PHASES ─────────────────────────────────────────────────────
else:
    with main_col:

        # ── CAMERA SETUP ──────────────────────────────────────────────
        if phase == "camera_setup":
            render_stepper(1)
            page_title("Camera Check", "Allow camera access — make sure you're well lit and centred.")
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            st.info(
                "Click START in the camera panel and allow microphone access. "
                "Your default system microphone is auto-detected."
            )

            if stream_ok:
                c1, c2, c3 = st.columns(3)
                c1.success("✓ Camera on")
                c2.success("✓ Face detected")
                if audio_ready:
                    c3.success("✓ Mic stream ready")
                else:
                    c3.warning("⚠ Mic not ready")
                st.markdown("""
                <div style="margin-top:16px;padding:16px 20px;background:#effaf4;
                     border-radius:12px;border:1px solid #b6f0cc">
                  <div style="font-size:14px;font-weight:600;color:#166534">
                    Everything looks good!</div>
                </div>""", unsafe_allow_html=True)

                if not st.session_state.get("camera_ready_confirmed"):
                    st.session_state.camera_ready_confirmed = True
                if not st.session_state.get("fullscreen_gate_shown"):
                    from proctoring_client import inject_fullscreen_gate
                    inject_fullscreen_gate()
                    st.session_state.fullscreen_gate_shown = True


                if not audio_ready:
                    st.warning("Microphone stream is not ready yet. Click STOP, then START again and allow microphone access before starting the interview.")
                elif st.button("▶  Start Interview", type="primary", use_container_width=True, key="cam_proceed"):
                    if st.session_state.get("jd_id"):
                        update_interview_status(
                            st.session_state.auth_username,
                            st.session_state.jd_id,
                            "In Progress"
                        )
                    st.components.v1.html("""
                    <script>
                        if (window.parent.__psEnterFullscreen) window.parent.__psEnterFullscreen();
                        if (window.parent.__psActivateProctoring) window.parent.__psActivateProctoring();
                    </script>
                    """, height=0)
                    go_to("prep")
            else:
                if stream_waiting:
                    st.warning("Camera permission was granted, but the video is still starting. Please wait a moment, or restart the camera if it stays stuck.")
                with st.expander("Camera or microphone not working?"):
                    st.info("If no camera appears, click SELECT DEVICE in the camera panel and choose your webcam.")
                    if st.button("Reset camera", key="reset_webrtc_devices"):
                        st.warning("Camera will restart. Wait a few seconds, then click START again.")
                        st.session_state.webrtc_reset_nonce += 1
                        st.session_state.audio_capture_started = False
                        st.session_state.audio_capture_processor_id = None
                        st.session_state._last_webrtc_diag = None
                        st.session_state._last_webrtc_ctx_id = None
                        time.sleep(2)
                        st.rerun()
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
                if stream_ok and ctx.video_processor:
                    ctx.video_processor.snapshot_and_reset()

            elapsed   = int(time.time() - st.session_state.prep_start)
            remaining = PREP_TIME - elapsed

            if remaining > 0:
                if stream_ok and ctx.video_processor:
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
                # Prep timer expired - initialize recording state
                if stream_ok and ctx.video_processor:
                    ctx.video_processor.set_countdown(None)
                
                st.session_state.record_container = {
                    "text": "", "done": False, "wav_path": None, "duration": 60, "error": None}
                st.session_state.audio_frames = []
                st.session_state.audio_capture_debug = ""
                st.session_state.audio_capture_started = False
                st.session_state.audio_capture_processor_id = None

                # Prime audio capture before entering recording to reduce first-tick races.
                if stream_ok and ctx.audio_processor:
                    try:
                        ctx.audio_processor.drain()
                        # Let local TTS/speaker bleed settle before arming capture.
                        time.sleep(AUDIO_REARM_DELAY_SEC)
                        ctx.audio_processor.start()
                        st.session_state.audio_capture_started = True
                        st.session_state.audio_capture_processor_id = id(ctx.audio_processor)
                        print("[PREP→RECORDING] Audio capture primed successfully")
                    except Exception as e:
                        st.session_state.audio_capture_started = False
                        st.session_state.audio_capture_processor_id = None
                        print(f"[PREP→RECORDING] Audio prime failed: {e}")
                
                if stream_ok and ctx.video_processor:
                    ctx.video_processor.snapshot_and_reset()

                # Start the recording timer after priming completes so users get full answer time.
                st.session_state.record_start = time.time()
                
                go_to("recording")

        # ── RECORDING ─────────────────────────────────────────────────
        elif phase == "recording":
            render_stepper(2)
            q     = QUESTIONS[st.session_state.q_index]
            q_num = st.session_state.q_index + 1
            q_tot = len(QUESTIONS)

            print("\n[RECORDING PHASE START]")
            print(f"  stream_ok={stream_ok}")
            print(f"  ctx.audio_processor={ctx.audio_processor}")
            print(f"  audio_processor_id={id(ctx.audio_processor) if ctx.audio_processor else None}")
            print(f"  audio_capture_started={st.session_state.get('audio_capture_started', 'NOT SET')}")
            print(f"[RECORDING PHASE] playing={ctx.state.playing}, signalling={ctx.state.signalling}")

            if st.session_state.get("record_start") is None:
                st.session_state.record_start = time.time()

            current_processor_id = id(ctx.audio_processor) if ctx.audio_processor else None
            previous_processor_id = st.session_state.get("audio_capture_processor_id")
            if current_processor_id and previous_processor_id and current_processor_id != previous_processor_id:
                # Streamlit reruns can swap processor instances; force re-arm on swap.
                st.session_state.audio_capture_started = False
                st.session_state.audio_capture_processor_id = None
                st.session_state.audio_capture_debug = "Audio processor refreshed; restarting microphone capture."
                print(
                    "[RECORDING] Audio processor changed "
                    f"{previous_processor_id} -> {current_processor_id}; re-arming capture"
                )

            if not ctx.state.playing:
                st.warning("Video stream is not playing. Go back to Camera Check and click START in the camera panel.")

            if not ctx.state.signalling:
                st.info("WebRTC signalling is still establishing. If capture fails, click STOP then START in the camera panel.")

            # Start/restart capture when not armed (for first render and processor swaps).
            if (
                stream_ok
                and ctx.audio_processor
                and not st.session_state.get("audio_capture_started", False)
            ):
                try:
                    rearm_started_at = time.time()
                    ctx.audio_processor.drain()   # clear TTS bleed
                    time.sleep(AUDIO_REARM_DELAY_SEC)
                    ctx.audio_processor.start()
                    rearm_elapsed = time.time() - rearm_started_at
                    if st.session_state.get("record_start") is not None:
                        st.session_state.record_start += rearm_elapsed
                    st.session_state.audio_capture_started = True
                    st.session_state.audio_capture_processor_id = id(ctx.audio_processor)
                    print(
                        "[RECORDING] Audio capture started on first render of recording phase "
                        f"(timer compensated by {rearm_elapsed:.2f}s)"
                    )
                except Exception as e:
                    st.session_state.audio_capture_started = False
                    st.session_state.audio_capture_processor_id = None
                    print(f"[RECORDING] Audio start failed: {e}")

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
            if stream_ok and ctx.video_processor:
                ctx.video_processor.set_countdown(None)

            if stream_ok and not ctx.audio_processor:
                st.error(
                    "🎤 Microphone stream not ready\n\n"
                    "Click STOP in the camera panel, then START again. "
                    "Make sure to allow microphone access when prompted."
                )
                st.session_state.audio_capture_debug = (
                    "Microphone stream is not ready (audio processor missing). "
                    "Click STOP, then START and re-allow microphone access."
                )

            # Continuously drain buffered frames while recording timer is active.
            if stream_ok and ctx.audio_processor and st.session_state.get("audio_capture_started") and remaining > 0:
                try:
                    tick_frames = ctx.audio_processor.pop_frames()
                    if tick_frames:
                        st.session_state.audio_frames.extend(tick_frames)
                        st.session_state.audio_capture_debug = (
                            f"Captured {len(st.session_state.audio_frames)} audio chunks so far."
                        )
                except Exception as e:
                    st.session_state.audio_capture_debug = f"Audio capture read failed: {e}"

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
                if st.session_state.get("audio_capture_debug"):
                    st.caption(st.session_state.audio_capture_debug)

                time.sleep(1)

                st.rerun()
            else:
                if stream_ok and ctx.video_processor:
                    score, absent, fem, multi_face = ctx.video_processor.snapshot_and_reset()
                    if score == 0.0: score = 5.0
                    st.session_state.proctoring_multi_face_total += multi_face
                else:
                    score, absent, fem = 5.0, 0.0, {"dominant": "neutral", "breakdown": {}}
                st.session_state.cur_engagement     = score
                st.session_state.cur_absence        = absent
                st.session_state.cur_facial_emotion = fem

                frames = list(st.session_state.get("audio_frames", []))
                if stream_ok and ctx.audio_processor:
                    try:
                        tail_frames = ctx.audio_processor.stop_and_get()
                        if tail_frames:
                            frames.extend(tail_frames)
                            st.session_state.audio_capture_debug = f"Got {len(tail_frames)} final frames."
                    except Exception as e:
                        st.session_state.audio_capture_debug = f"Audio capture stop failed: {e}"
                st.session_state.audio_frames = frames
                st.session_state.audio_capture_started = False
                st.session_state.audio_capture_processor_id = None

                # Save browser audio frames to WAV, then transcribe
                frames = st.session_state.get("audio_frames", [])
                print(f"[RECORDING→PROCESSING] Collected {len(frames)} audio frames")
                
                if frames:
                    st.session_state.audio_capture_debug = (
                        f"Captured {len(frames)} audio chunks for transcription."
                    )
                    st.session_state.record_container["error"] = None
                    detected_sr = (
                        int(getattr(ctx.audio_processor, "sample_rate", 48000))
                        if ctx.audio_processor else 48000
                    )
                    wav_path = save_audio_frames_to_wav(frames, sample_rate=detected_sr)
                    
                    if wav_path:
                        print(f"[RECORDING→PROCESSING] WAV file created: {wav_path}")
                        # Pass per-question keywords into container so
                        # build_keyword_prompt() uses ONLY terms relevant to
                        # THIS question — prevents Whisper hallucination.
                        q_idx = st.session_state.q_index
                        st.session_state.record_container["question"] = q
                        st.session_state.record_container["vocab"] = (
                            _build_transcription_vocab_for_question(q_idx)
                        )
                        transcribe_wav(
                            wav_path,
                            st.session_state.record_container,
                            RECORD_TIME,
                            prompt="",  # let build_keyword_prompt() handle it
                        )
                    else:
                        print("[RECORDING→PROCESSING] WAV creation failed")
                        st.session_state.record_container.update({
                            "text": "",
                            "wav_path": None,
                            "duration": RECORD_TIME,
                            "done": True,
                            "error": "Failed to process audio. Please check microphone and try again."
                        })
                else:
                    # No captured browser audio: finish immediately so UI does not
                    # stall in processing for another full recording window.
                    print("[RECORDING→PROCESSING] No audio frames captured!")
                    st.session_state.audio_capture_debug = (
                        "No audio was captured from your microphone.\n\n"
                        "Possible causes:\n"
                        "• Microphone permission not granted\n"
                        "• Wrong microphone selected\n"
                        "• Microphone muted in Windows\n\n"
                        "Please return to Camera Check and ensure microphone access is allowed."
                    )
                    st.session_state.record_container.update({
                        "text": "",
                        "wav_path": None,
                        "duration": RECORD_TIME,
                        "done": True,
                        "error": "No audio captured. Please check microphone permissions and try again."
                    })

                st.session_state.audio_frames = []  # clear for next question
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
            error_msg = st.session_state.record_container.get("error")
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

            if error_msg:
                st.error(f"{error_msg}")
                if "microphone" in error_msg.lower():
                    with st.expander("Microphone troubleshooting"):
                        st.markdown(
                            "1. Open Windows Settings -> Sound -> Input devices.\n"
                            "2. Set your intended microphone as default input device.\n"
                            "3. Test microphone in Voice Recorder.\n"
                            "4. Return to Camera Check, click STOP then START, and allow browser permission."
                        )

            if not has_ans and st.session_state.get("audio_capture_debug"):
                st.info(st.session_state.audio_capture_debug)

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
                        st.session_state.audio_capture_started = False
                        st.session_state.audio_capture_processor_id = None
                        st.session_state.record_container = {
                            "text": "", "done": False, "wav_path": None, "duration": 60, "error": None}
                        st.session_state.audio_frames     = []  # clear old frames
                        st.session_state.record_start     = time.time()
                        if stream_ok and ctx.video_processor:
                            ctx.video_processor.snapshot_and_reset()
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
                        er = requests.post(f"{ANSWER_SERVICE_URL}/evaluate_answer",
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
                        _ej = requests.post(f"{EMOTION_SERVICE_URL}/predict_detail",
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
                    st.session_state.audio_capture_started = False
                    st.session_state.audio_capture_processor_id = None
                    st.session_state.audio_frames = []

                    if st.session_state.q_index >= len(QUESTIONS):
                        go_to("report")
                    else:
                        go_to("prep")
