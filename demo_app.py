import streamlit as st
import requests
import plotly.graph_objects as go
import time
from whisper_audio import record_answer_background
from voice_question import speak_question
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode
from engagement_realtime import EngagementDetector
import av   
from database import save_session, init_db
init_db()
# Force mediapipe to load before tensorflow loads from other services
try:
    import mediapipe as mp
    _test_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True, max_num_faces=1,
        min_detection_confidence=0.5, min_tracking_confidence=0.5
    )
    _test_mesh.close()
    del _test_mesh
    print("✅ mediapipe pre-loaded successfully")
except Exception as e:
    print(f"mediapipe pre-load failed: {e}")
st.set_page_config(page_title="PsySense Interview", layout="centered")

st.markdown("""
<style>
button[kind="secondary"] { display: none !important; }
</style>
<script>
(function hideStop() {
    const kill = () => {
        document.querySelectorAll('button').forEach(b => {
            if (b.textContent.trim() === 'STOP') b.style.cssText = 'display:none!important';
        });
    };
    kill();
    new MutationObserver(kill).observe(document.body, {childList:true, subtree:true});
})();
</script>
""", unsafe_allow_html=True)


class EngagementProcessor(VideoProcessorBase):
    def __init__(self):
        self.detector = EngagementDetector()

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        processed = self.detector.process_frame(img)
        return av.VideoFrame.from_ndarray(processed, format="bgr24")

    def get_avg_score(self):
        return self.detector.get_avg_score()
    def set_countdown(self, value):
        self.detector.set_countdown(value)
    def get_absence_ratio(self):
        return self.detector.get_absence_ratio()

    
    def get_emotion_summary(self):
        return self.detector.get_emotion_summary()

    def snapshot_and_reset(self):
        score  = self.detector.get_avg_score()
        absent = self.detector.get_absence_ratio()
        emotion = self.detector.get_emotion_summary()   # NEW
        self.detector.reset_session()
        return score, absent, emotion  

QUESTIONS = [
    "Tell me about yourself.",
    #"What are the challenges you have faced?",
    #"Describe a time you worked in a team to solve a problem.",
    #"Where do you see yourself in 5 years?",
    #"Why should we hire you?",
]
PREP_TIME   = 15
RECORD_TIME = 60

st.title("🧠 PsySense AI Mock Interview")

# ── Session state ──────────────────────────────────────────────────────────
defaults = {
    "phase": "start",
    "q_index": 0,
    "candidate_name": "",
    "question_spoken": False,
    "session_saved": False,
    "prep_start": None,
    "record_start": None,
    "retry_used": False,
    "record_container": {"text": "", "done": False, "wav_path": None, "duration": 60},
    "answer_input": "",
    "cognitive_scores": [],
    "emotion_scores": [],
    "engagement_scores": [],
    "absence_ratios": [],
    "low_presence_flags": [],
    "question_history": [],
    "answer_history": [],
    "cur_engagement": None,
    "cur_absence": None,
    "cur_facial_emotion": {"dominant": "neutral", "breakdown": {}},
    "speech_breakdowns": [],  # per-question detail from /predict_detail
    "facial_emotions": [],
  # per-question detail from /predict_detail
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

phase = st.session_state.phase


def go_to(p):
    st.session_state.phase = p
    st.rerun()


# ══════════════════════════════════════════════════════════════════════
# START SCREEN
# ══════════════════════════════════════════════════════════════════════
if phase == "start":
    st.markdown("## Ready for your mock interview")
    st.write(
        "You will be asked **5 behavioral questions**. "
        "After clicking Start, allow camera access **once** — "
        "the camera stays on for the full interview."
    )
    st.info("💡 Allow camera permission when your browser asks. The interview begins automatically after that.")
    candidate_name = st.text_input("Candidate Name", placeholder="Enter your full name")
    if st.button("🚀 Start Interview", type="primary"):
        if not candidate_name.strip():
            st.warning("Please enter your name before starting.")
        else:
            st.session_state["candidate_name"] = candidate_name.strip()
            go_to("camera_setup")

# ══════════════════════════════════════════════════════════════════════
# ALL INTERVIEW PHASES (camera rendered once, persists across phases)
# ══════════════════════════════════════════════════════════════════════
elif phase != "report":

    # Camera widget — same key every render = same WebRTC connection
    ctx = webrtc_streamer(
        key="engagement",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=EngagementProcessor,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )
    stream_ok = ctx.state.playing and ctx.video_processor is not None

    # ── CAMERA SETUP: wait for user to click START in WebRTC widget ───
    if phase == "camera_setup":
        if stream_ok:
            st.success("✅ Camera connected! Starting interview...")
            time.sleep(1)
            go_to("prep")
        else:
            st.warning("👆 Click the **START** button above to turn on your camera. The interview will begin automatically.")
            time.sleep(1)
            st.rerun()

    # ── PREP TIMER ────────────────────────────────────────────────────
    elif phase == "prep":
        q = QUESTIONS[st.session_state.q_index]
        st.subheader(f"Question {st.session_state.q_index + 1}/{len(QUESTIONS)}")
        st.write(q)

        # Clear stale scores from previous question so they don't show during prep
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
            st.progress((PREP_TIME - remaining) / PREP_TIME)
            if not stream_ok:
                st.warning("⚠️ Camera not connected.")
            time.sleep(1)
            st.rerun()
        else:
            if stream_ok:
                ctx.video_processor.set_countdown(None)
            st.session_state.record_container = {"text": "", "done": False, "wav_path": None, "duration": 60}
            st.session_state.record_start     = time.time()
            if stream_ok:
                ctx.video_processor.snapshot_and_reset()
            record_answer_background(st.session_state.record_container, RECORD_TIME)
            go_to("recording")
            st.session_state.record_start     = time.time()
            if stream_ok:
                ctx.video_processor.snapshot_and_reset()  # clear prep frames
            record_answer_background(st.session_state.record_container, RECORD_TIME)
            go_to("recording")

    # ── RECORDING ────────────────────────────────────────────────────
    elif phase == "recording":
        q = QUESTIONS[st.session_state.q_index]
        st.subheader(f"Question {st.session_state.q_index + 1}/{len(QUESTIONS)}")
        st.write(q)

        if stream_ok:
            absence = ctx.video_processor.get_absence_ratio()
            if absence > 0.30:
                st.error(f"⚠️ Face not visible {absence*100:.0f}% of the time — stay in frame!")
            elif absence > 0.15:
                st.warning(f"👁 Face absent {absence*100:.0f}% — look at the camera")

        elapsed   = int(time.time() - st.session_state.record_start)
        remaining = RECORD_TIME - elapsed

        if stream_ok:
            ctx.video_processor.set_countdown(None)  # ensure cleared during recording
        if remaining > 0:
            st.warning("🔴 Recording in progress...")
            st.write(f"{remaining} sec left")
            st.progress((RECORD_TIME - remaining) / RECORD_TIME)
            time.sleep(1)
            st.rerun()
        else:
            if stream_ok:
                score, absent, facial_emotion = ctx.video_processor.snapshot_and_reset()
                if score == 0.0:
                    score = 5.0
            else:
                score, absent, facial_emotion = 5.0, 0.0, {"dominant": "neutral", "breakdown": {}}
            st.session_state.cur_engagement     = score
            st.session_state.cur_absence        = absent
            st.session_state.cur_facial_emotion = facial_emotion
            go_to("processing")

    # ── PROCESSING ───────────────────────────────────────────────────
    elif phase == "processing":
        q = QUESTIONS[st.session_state.q_index]
        st.subheader(f"Question {st.session_state.q_index + 1}/{len(QUESTIONS)}")
        st.write(q)

        if not st.session_state.record_container["done"]:
            st.info("⏳ Processing your answer...")
            time.sleep(1)
            st.rerun()
        else:
            st.session_state.answer_input = st.session_state.record_container["text"]
            go_to("transcript")

    # ── TRANSCRIPT + SUBMIT ──────────────────────────────────────────
    elif phase == "transcript":
        q   = QUESTIONS[st.session_state.q_index]
        ans = st.session_state.answer_input
        eng = st.session_state.cur_engagement   # None during prep, set after recording
        abr = st.session_state.cur_absence

        st.subheader(f"Question {st.session_state.q_index + 1}/{len(QUESTIONS)}")
        st.write(q)
        st.markdown("**Your Answer (Transcript)**")
        st.info(ans if ans else "_No speech detected — please re-record._")

        # Only show engagement if we have a real recorded value
        if eng is not None and abr is not None:
            col_e, col_a = st.columns(2)
            col_e.metric(
                f"{'🟢' if eng >= 7 else '🟡' if eng >= 4 else '🔴'} Engagement Score",
                f"{eng} / 10"
            )
            col_a.metric(
                f"{'🔴' if abr > 0.30 else '🟡' if abr > 0.15 else '🟢'} Face Absent",
                f"{abr*100:.0f}%"
            )
            if abr > 0.30:
                st.error("⚠️ Low face presence detected.")

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            if not st.session_state.retry_used:
                if st.button("🔁 Re-record"):
                    st.session_state.retry_used       = True
                    st.session_state.record_container = {"text": "", "done": False, "wav_path": None, "duration": 60}
                    st.session_state.record_start     = time.time()
                    if stream_ok:
                        ctx.video_processor.snapshot_and_reset()
                    record_answer_background(st.session_state.record_container, RECORD_TIME)
                    go_to("recording")

        with col2:
            if st.button("✅ Submit", type="primary"):
                try:
                    cog = requests.post(
                        "http://127.0.0.1:8000/evaluate_answer",
                        json={"question": q, "answer": ans}
                    ).json()["cognitive_score"]
                except Exception:
                    st.error("Answer service not responding — fallback used.")
                    cog = 5.0

                try:
                    _wav  = st.session_state.record_container.get("wav_path")
                    _dur  = st.session_state.record_container.get("duration", 60)
                    # Use /predict_detail to get full breakdown for report
                    _emo_res  = requests.post(
                        "http://127.0.0.1:8002/predict_detail",
                        json={
                            "text":             ans,
                            "wav_path":         _wav,
                            "duration_seconds": _dur
                        },
                        timeout=30
                    )
                    _emo_json = _emo_res.json()
                    emo = float(_emo_json.get("emotion_score", 5.0))

                    # Store full breakdown for report display
                    st.session_state.speech_breakdowns.append(_emo_json)

                    # Delete WAV file after voice scoring
                    if _wav:
                        import os as _os
                        try: _os.unlink(_wav)
                        except Exception: pass

                except Exception as _e:
                    st.warning(f"Speech scoring error: {_e}")
                    emo = 5.0
                    st.session_state.speech_breakdowns.append({})

                st.session_state.cognitive_scores.append(cog)
                st.session_state.emotion_scores.append(emo)
                st.session_state.engagement_scores.append(eng if eng is not None else 5.0)
                st.session_state.absence_ratios.append(abr if abr is not None else 0.0)
                st.session_state.low_presence_flags.append((abr or 0.0) > 0.30)
                st.session_state.question_history.append(q)
                st.session_state.answer_history.append(ans)
                st.session_state.facial_emotions.append(
                    st.session_state.get("cur_facial_emotion", {"dominant": "neutral", "breakdown": {}})
                )
                st.session_state.q_index        += 1
                st.session_state.question_spoken = False
                st.session_state.retry_used      = False
                st.session_state.cur_engagement  = None
                st.session_state.cur_absence     = None

                if st.session_state.q_index >= len(QUESTIONS):
                    go_to("report")
                else:
                    go_to("prep")

# ══════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ══════════════════════════════════════════════════════════════════════
elif phase == "report":

    st.header("📊 PsySense Interview Report")

    avg_cog = sum(st.session_state.cognitive_scores)  / len(st.session_state.cognitive_scores)
    avg_emo = sum(st.session_state.emotion_scores)    / len(st.session_state.emotion_scores)
    avg_eng = sum(st.session_state.engagement_scores) / len(st.session_state.engagement_scores)

    try:
        fusion_res = requests.post(
            "http://127.0.0.1:8001/fuse",
            json={"cognitive_score": avg_cog, "emotion_score": avg_emo, "engagement_score": avg_eng}
        ).json()
    except Exception:
        st.error("Fusion service not responding.")
        fusion_res = {"final_behavioral_score": 0, "readiness_level": "Unknown"}

    try:
        insight_res = requests.post(
            "http://127.0.0.1:8003/generate_insight",
            json={
                "avg_cognitive": avg_cog, "avg_emotion": avg_emo,
                "avg_engagement": avg_eng,
                "final_score": fusion_res["final_behavioral_score"]
            },
            timeout=30
        ).json()
    except Exception:
        st.error("Insight service not responding.")
        insight_res = {
            "strengths": ["Insight unavailable"],
            "weaknesses": ["Insight unavailable"],
            "recommendation": "Unknown"
        }

    final_score = fusion_res["final_behavioral_score"]
    readiness   = fusion_res["readiness_level"]

    if not st.session_state.get("session_saved", False):
        save_session(
            candidate_name=st.session_state.get("candidate_name", "Unknown"),
            final_score=final_score,
            cognitive_score=avg_cog,
            emotion_score=avg_emo,
            engagement_score=avg_eng,
            questions_answered=len(st.session_state.question_history)
        )
        st.session_state["session_saved"] = True
   
    # ── Human-readable score explanation ────────────────────────────────
    # What does each dimension actually mean in plain English?
    def score_label(s):
        if s >= 8: return "Excellent"
        if s >= 6: return "Good"
        if s >= 4: return "Average"
        return "Needs Work"

    def score_color(s):
        if s >= 8: return "🟢"
        if s >= 6: return "🟡"
        if s >= 4: return "🟠"
        return "🔴"

    # ── Overall result banner ────────────────────────────────────────────
    if final_score >= 75:
        st.success(f"🎉 Overall Result: **{readiness}** — Score {final_score}/100")
    elif final_score >= 55:
        st.info(f"👍 Overall Result: **{readiness}** — Score {final_score}/100")
    elif final_score >= 35:
        st.warning(f"📈 Overall Result: **{readiness}** — Score {final_score}/100")
    else:
        st.error(f"💪 Overall Result: **{readiness}** — Score {final_score}/100")

    # ── What each score means — human readable ───────────────────────────
    st.markdown("### What the scores mean")
    st.markdown(
        """
| Dimension | What it measures | Your Score | Level |
|-----------|-----------------|------------|-------|
| 🧠 Answer Quality | How clearly and logically you answered — structure, depth, examples given | """ +
        f"{round(avg_cog,1)}/10" + " | " + score_color(avg_cog) + " " + score_label(avg_cog) + """ |
| 😊 Emotional Tone | How confident and stable you sounded — calm vs stressed | """ +
        f"{round(avg_emo,1)}/10" + " | " + score_color(avg_emo) + " " + score_label(avg_emo) + """ |
| 👁️ Attentiveness | How engaged and focused you appeared — eye contact, face visible, stable | """ +
        f"{round(avg_eng,1)}/10" + " | " + score_color(avg_eng) + " " + score_label(avg_eng) + """ |
"""
    )

    st.markdown("---")

    # ── Gauge ────────────────────────────────────────────────────────────
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=final_score,
        title={"text": "Overall Interview Score"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar":  {"color": "#1D9E75"},
            "steps": [
                {"range": [0,  35],  "color": "#FCEBEB"},
                {"range": [35, 55],  "color": "#FAEEDA"},
                {"range": [55, 75],  "color": "#E1F5EE"},
                {"range": [75, 100], "color": "#9FE1CB"},
            ],
            "threshold": {
                "line": {"color": "#185FA5", "width": 3},
                "thickness": 0.75,
                "value": final_score
            }
        }
    ))
    st.plotly_chart(fig_gauge, use_container_width=True)

    # ── Bar chart ────────────────────────────────────────────────────────
    fig_bar = go.Figure(data=[go.Bar(
        x=["Answer Quality", "Emotional Tone", "Attentiveness"],
        y=[avg_cog, avg_emo, avg_eng],
        marker_color=["#4C9ED9", "#E8825A", "#5DCAA5"],
        text=[f"{round(avg_cog,1)}", f"{round(avg_emo,1)}", f"{round(avg_eng,1)}"],
        textposition="outside"
    )])
    fig_bar.update_layout(
        title="Score Breakdown (out of 10)",
        yaxis=dict(range=[0, 11]),
        showlegend=False
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # ── Trend graph — always shown, even for 1 question ─────────────────
    st.markdown("### How you performed across questions")
    qs     = list(range(1, len(st.session_state.cognitive_scores) + 1))
    qlabels = [f"Q{i}" for i in qs]

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=qlabels, y=st.session_state.cognitive_scores,
        mode="lines+markers", name="Answer Quality",
        line=dict(color="#4C9ED9", width=2),
        marker=dict(size=8)
    ))
    fig_trend.add_trace(go.Scatter(
        x=qlabels, y=st.session_state.emotion_scores,
        mode="lines+markers", name="Emotional Tone",
        line=dict(color="#E8825A", width=2),
        marker=dict(size=8)
    ))
    fig_trend.add_trace(go.Scatter(
        x=qlabels, y=st.session_state.engagement_scores,
        mode="lines+markers", name="Attentiveness",
        line=dict(color="#5DCAA5", width=2),
        marker=dict(size=8)
    ))
    fig_trend.update_layout(
        yaxis=dict(range=[0, 10], title="Score"),
        xaxis_title="Question",
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified"
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    flagged = [i+1 for i, f in enumerate(st.session_state.low_presence_flags) if f]
    if flagged:
        st.warning(f"⚠️ Camera was not fully visible in question(s): {flagged}. Attentiveness score may be lower than actual.")

    # ── Recruiter insight ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Recruiter Assessment")

    col_s, col_w = st.columns(2)
    with col_s:
        st.markdown("**✅ Strengths**")
        for s in insight_res["strengths"]:
            st.markdown(f"- {s}")
    with col_w:
        st.markdown("**⚠️ Areas to Improve**")
        for w in insight_res["weaknesses"]:
            st.markdown(f"- {w}")

    st.markdown(f"**⭐ Hiring Recommendation:** {insight_res['recommendation']}")

    st.markdown("---")
    # Overall facial emotion summary
    all_emotions = {}
    for fe in st.session_state.get("facial_emotions", []):
        for emotion, pct in fe.get("breakdown", {}).items():
            all_emotions[emotion] = all_emotions.get(emotion, 0) + pct

    if all_emotions:
        total = sum(all_emotions.values())
        overall = {e: round((v/total)*100, 1) for e, v in sorted(all_emotions.items(), key=lambda x: x[1], reverse=True)}
        dominant_overall = max(all_emotions, key=all_emotions.get)

        emotion_emoji = {
            "happy": "😊", "neutral": "😐", "sad": "😢",
            "angry": "😠", "fear": "😰", "surprise": "😲",
            "disgust": "😑"
        }
        confidence_label = {
            "happy": "Confident", "neutral": "Composed",
            "surprise": "Caught off guard", "fear": "Nervous",
            "sad": "Low energy", "angry": "Stressed",
            "disgust": "Uncomfortable"
        }

        st.markdown("---")
        st.markdown("### 😶 Overall Facial Emotion — Full Interview")
        st.info(f"{emotion_emoji.get(dominant_overall, '😐')} Throughout the interview the candidate appeared predominantly **{confidence_label.get(dominant_overall, dominant_overall).lower()}**")

        for emotion, pct in list(overall.items())[:4]:
            e = emotion_emoji.get(emotion, "😐")
            st.write(f"{e} {emotion.capitalize()}")
            st.progress(pct / 100)
            st.caption(f"{pct}%")

    # ── Per-question breakdown ───────────────────────────────────────────
    st.markdown("### Question-by-question breakdown")
    for i in range(len(st.session_state.question_history)):
        with st.expander(f"Question {i+1}: {st.session_state.question_history[i]}"):
            st.markdown("**Your answer:**")
            st.info(st.session_state.answer_history[i])

            cog_i = st.session_state.cognitive_scores[i]
            emo_i = st.session_state.emotion_scores[i]
            eng_i = st.session_state.engagement_scores[i]
            abs_i = st.session_state.absence_ratios[i]     if i < len(st.session_state.absence_ratios)     else 0
            low_i = st.session_state.low_presence_flags[i] if i < len(st.session_state.low_presence_flags) else False

            qc1, qc2, qc3, qc4 = st.columns(4)
            qc1.metric("Answer Quality",  f"{round(cog_i,1)}/10", help="How clearly and logically you answered")
            qc2.metric("Emotional Tone",  f"{round(emo_i,1)}/10", help="How confident and calm you sounded")
            qc3.metric("Attentiveness",   f"{round(eng_i,1)}/10 {'⚠️' if low_i else ''}", help="How engaged and focused you appeared")
            qc4.metric("Camera Visible",  f"{100 - abs_i*100:.0f}%", help="Percentage of time your face was clearly visible")

            if low_i:
                st.caption("⚠️ Camera not fully visible for this answer — attentiveness score may be lower than actual.")

            # ── Speech Quality Breakdown card ─────────────────────────────
            if i < len(st.session_state.speech_breakdowns):
                sb = st.session_state.speech_breakdowns[i]
                if sb:
                    st.markdown("**😊 Speech Quality Breakdown**")
                    em_score  = sb.get("emotion_model",   5.0)
                    fl_score  = sb.get("fluency_score",   5.0)
                    vo_score  = sb.get("voice_score",     5.0)
                    dominant  = sb.get("dominant_emotion", "neutral")
                    combined  = sb.get("emotion_score",   5.0)

                    bc1, bc2, bc3 = st.columns(3)
                    bc1.metric(
                        "🤖 Emotion Model",
                        f"{em_score}/10",
                        help="Your custom DistilBERT model — detects pride, nervousness, confidence from words"
                    )
                    bc2.metric(
                        "🗣️ Fluency",
                        f"{fl_score}/10",
                        help="Measures filler words (um, uh, like), speaking pace, and incomplete sentences"
                    )
                    bc3.metric(
                        "🎙️ Voice Confidence",
                        f"{vo_score}/10",
                        help="Measures pitch variation, voice energy, and silence ratio from audio"
                    )

                    # Dominant emotion from your model
                    emotion_emoji = {
                        "pride": "🏆", "joy": "😊", "optimism": "⭐",
                        "excitement": "🎉", "gratitude": "🙏", "neutral": "😐",
                        "nervousness": "😰", "confusion": "😕", "fear": "😨",
                        "disappointment": "😞", "approval": "👍", "admiration": "✨"
                    }
                    emoji = emotion_emoji.get(dominant, "💬")
                    st.caption(
                        f"{emoji} Dominant emotion detected: **{dominant.capitalize()}** | "
                        f"Combined speech score: **{combined}/10** "
                        f"(34% emotion model + 33% fluency + 33% voice)"
                    )

            # Facial emotion card
            if i < len(st.session_state.get("facial_emotions", [])):
                fe = st.session_state.facial_emotions[i]
                if fe and fe.get("breakdown"):
                    st.markdown("**😶 Facial Emotion During Answer**")
                    dominant = fe["dominant"]
                    breakdown = fe["breakdown"]

                    emotion_emoji = {
                        "happy": "😊", "neutral": "😐", "sad": "😢",
                        "angry": "😠", "fear": "😰", "surprise": "😲",
                        "disgust": "😑"
                    }
                    confidence_label = {
                        "happy": "Confident", "neutral": "Composed",
                        "surprise": "Caught off guard", "fear": "Nervous",
                        "sad": "Low energy", "angry": "Stressed",
                        "disgust": "Uncomfortable"
                    }
                    emoji = emotion_emoji.get(dominant, "😐")
                    label = confidence_label.get(dominant, dominant.capitalize())

                    st.info(f"{emoji} Dominant facial expression: **{label}** ({dominant})")

                    top3 = list(breakdown.items())[:3]
                    for emotion, pct in top3:
                        e = emotion_emoji.get(emotion, "😐")
                        st.write(f"{e} {emotion.capitalize()}")
                        st.progress(pct / 100)
                        st.caption(f"{pct}%")

    st.markdown("---")
    
    # ── Restart button — always visible at bottom ────────────────────────
    st.markdown("### Try again?")
    st.write("Practice makes perfect. Each attempt you can see exactly where you improved.")
    if st.button("🔄 Start New Interview", type="primary", use_container_width=True):
        st.session_state.clear()
        st.rerun()