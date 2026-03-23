"""
emotion_service/main.py
-----------------------
Speech Quality Service — Port 8002

Now measures:
- Fluency (filler words, pace, completeness) from transcript
- Voice confidence (pitch, energy, silence) from WAV file

Run with:
    uvicorn emotion_service.main:app --port 8002 --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from emotion_service.emotion_model import predict_emotion_score, predict_emotion_detail

app = FastAPI(title="PsySense Speech Quality Service", version="2.0")


class EmotionRequest(BaseModel):
    text:             str
    wav_path:         Optional[str] = None   # WAV file path for voice scoring
    duration_seconds: Optional[int] = 60     # recording duration for WPM


@app.get("/")
def root():
    return {
        "message": "Speech Quality Service Running",
        "version": "2.0",
        "signals": ["fluency", "voice_confidence"]
    }


@app.post("/predict")
def predict(req: EmotionRequest):
    score = predict_emotion_score(
        text             = req.text,
        wav_path         = req.wav_path,
        duration_seconds = req.duration_seconds or 60
    )
    return {"emotion_score": score}


@app.post("/predict_detail")
def predict_detail(req: EmotionRequest):
    """Extended endpoint with full breakdown — for debugging."""
    return predict_emotion_detail(
        text             = req.text,
        wav_path         = req.wav_path,
        duration_seconds = req.duration_seconds or 60
    )