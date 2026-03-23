# 🧠 PsySense — Multimodal AI Behavioral Interview Assessment System

> An AI-powered proctoring system that evaluates candidates across three signals simultaneously: cognitive reasoning, speech quality, and visual engagement — producing a weighted behavioral score for recruiters.

---

## 🎯 What it does

PsySense conducts automated behavioral interviews and scores candidates on:

| Signal | What it measures | Weight |
|--------|-----------------|--------|
| 🧠 Answer Quality | LLM evaluates answer structure, depth, relevance, clarity | 50% |
| 😊 Emotional Tone | DistilBERT emotion model + librosa voice prosody + fluency analysis | 30% |
| 👁️ Attentiveness | OpenCV face detection — gaze, presence, head stability via WebRTC | 20% |

Final score: `0.5 × cognitive + 0.3 × emotion + 0.2 × engagement`

---

## 🏗️ Architecture
```
┌─────────────────────────────────────────────────────┐
│                  Streamlit UI (8501)                 │
│         WebRTC Camera + Phase State Machine          │
└──────────┬──────────────┬──────────────┬────────────┘
           │              │              │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌───▼────────────┐
    │   Answer    │ │  Emotion   │ │   Engagement   │
    │  Service   │ │  Service   │ │   (OpenCV)     │
    │  (8000)    │ │  (8002)    │ │   Real-time    │
    │  LLM+Groq  │ │ DistilBERT │ │   WebRTC       │
    └──────┬──────┘ └─────┬──────┘ └───┬────────────┘
           │              │              │
    ┌──────▼──────────────▼──────────────▼────────────┐
    │              Fusion Service (8001)               │
    │         Weighted score combination               │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │              Insight Service (8003)              │
    │     Strengths / Weaknesses / Recommendation      │
    └──────────────────────┬──────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────────┐
    │           Recruiter Dashboard + SQLite           │
    │        Candidate ranking + PDF export            │
    └─────────────────────────────────────────────────┘
```

---

## 🔬 Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit, streamlit-webrtc |
| Speech Transcription | OpenAI Whisper (small) |
| LLM Scoring | Groq API (LLaMA 3.1 8B) |
| Emotion Model | Custom DistilBERT — [Hitan2004/psysense-emotion-ai](https://huggingface.co/Hitan2004/psysense-emotion-ai) |
| Voice Analysis | librosa (pitch, energy, silence ratio) |
| Face Tracking | OpenCV Haar Cascade |
| Backend | FastAPI + Uvicorn (5 microservices) |
| Database | SQLite + SQLAlchemy |
| PDF Export | fpdf2 |

---

## 📊 Verified Results

| Candidate Type | Final Score |
|----------------|-------------|
| Weak answers, unfocused | ~48/100 |
| Strong answers, structured | ~76/100 |
| **Gap** | **~28 points** |

---

## 🚀 Running Locally

### Prerequisites
- Python 3.10
- Groq API key (get one at [console.groq.com](https://console.groq.com))

### Setup
```bash
git clone https://github.com/Hitan547/ai-behavioral-interviewer-proctoring.git
cd ai-behavioral-interviewer-proctoring

python -m venv venv310
venv310\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Environment

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_groq_api_key_here
```

### Run
```bash
.\run_system.bat
```

Opens at `http://localhost:8501`

---

## 🗂️ Project Structure
```
├── demo_app.py              # Streamlit UI — phase state machine
├── engagement_realtime.py   # OpenCV face engagement detector
├── whisper_audio.py         # Background audio recorder + Whisper
├── fluency_scorer.py        # Filler words, pace, completeness
├── voice_scorer.py          # librosa pitch/energy/silence
├── database.py              # SQLite session storage
├── pdf_export.py            # Candidate PDF report generator
├── answer_service/          # LLM cognitive scoring (port 8000)
├── emotion_service/         # Speech quality scoring (port 8002)
├── fusion_service/          # Score fusion (port 8001)
├── insight_service/         # Recruiter insights (port 8003)
├── engagement_service/      # Standalone engagement API (port 8004)
└── pages/dashboard.py       # Recruiter dashboard
```

---

## 🧠 Emotion Model

Custom DistilBERT classifier trained on GoEmotions (28 labels) — deployed to HuggingFace.

Combined with fluency and voice scoring:
```
speech_score = 0.34 × emotion_model + 0.33 × fluency + 0.33 × voice
```

→ [View model on HuggingFace](https://huggingface.co/Hitan2004/psysense-emotion-ai)

---

## 👨‍💻 Built by

**Hitan K** — AIML Engineering Intern @ DIGITALTRANSOLS AI PRIVATE LIMITED

[LinkedIn](https://www.linkedin.com/in/hitan-k-59425527b) · [GitHub](https://github.com/Hitan547)
