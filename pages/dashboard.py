import streamlit as st
import pandas as pd
from database import get_all_sessions, get_session_by_id, init_db
from pdf_export import generate_pdf

st.set_page_config(page_title="PsySense Recruiter Dashboard", layout="wide")
st.title("🧠 PsySense — Recruiter Dashboard")

init_db()
sessions = get_all_sessions()

if not sessions:
    st.info("No candidate sessions yet. Run an interview first.")
    st.stop()

# --- Build dataframe ---
rows = []
for s in sessions:
    rows.append({
        "ID": s.id,
        "Candidate": s.candidate_name,
        "Date": s.created_at.strftime("%d %b %Y, %H:%M"),
        "Final Score": s.final_score,
        "Answer Quality": s.cognitive_score,
        "Emotional Tone": s.emotion_score,
        "Attentiveness": s.engagement_score,
        "Qs Answered": s.questions_answered,
        "Flagged": "🚩 Yes" if s.flagged else "✅ No",
    })

df = pd.DataFrame(rows)

# --- Summary metrics ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Candidates", len(df))
col2.metric("Avg Score", f"{df['Final Score'].mean():.1f}")
col3.metric("Flagged", int((df["Flagged"] == "🚩 Yes").sum()))
col4.metric("Top Score", f"{df['Final Score'].max():.1f}")

st.divider()

# --- Colour-code rows by score ---
def colour_score(val):
    if isinstance(val, float):
        if val >= 70:
            return "color: #2ecc71; font-weight: bold"
        elif val < 50:
            return "color: #e74c3c; font-weight: bold"
    return ""

styled = (
    df.drop(columns=["ID"])
    .style
    .applymap(colour_score, subset=["Final Score", "Answer Quality", "Emotional Tone", "Attentiveness"])
)

st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# --- PDF Export ---
st.subheader("📄 Export Candidate Report")
candidate_ids = {f"{s.candidate_name} — {s.created_at.strftime('%d %b %Y, %H:%M')} (ID {s.id})": s.id for s in sessions}
selected = st.selectbox("Select candidate", list(candidate_ids.keys()))

if st.button("Generate PDF Report"):
    session_id = candidate_ids[selected]
    session = get_session_by_id(session_id)
    pdf_path = generate_pdf(session)
    with open(pdf_path, "rb") as f:
        st.download_button(
            label="⬇️ Download PDF",
            data=f,
            file_name=f"psysense_{session.candidate_name.replace(' ', '_')}.pdf",
            mime="application/pdf"
        )