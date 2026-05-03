"""
emotion_service/main.py
-----------------------
Delivery Quality Service — Port 8002

Now measures:
- Fluency (filler words, pace, completeness) from transcript
- Voice/prosody (pitch, energy, silence) from WAV file

Run with:
    uvicorn emotion_service.main:app --port 8002 --reload
"""

import base64
import os
import tempfile

from fastapi import FastAPI
from pydantic import BaseModel, validator
from typing import Optional, Tuple

from emotion_service.emotion_model import predict_emotion_score, predict_emotion_detail

app = FastAPI(title="PsySense Delivery Quality Service", version="2.0")


class EmotionRequest(BaseModel):
    text:             str
    wav_path:         Optional[str] = None   # legacy local path (dev only)
    wav_base64:       Optional[str] = None   # base64 WAV bytes (deployment-safe)
    duration_seconds: Optional[int] = 60

    @validator("duration_seconds", pre=True, always=True)
    def clamp_duration(cls, v):
        try:
            duration = int(v) if v is not None else 60
        except Exception:
            duration = 60
        return max(duration, 1)


def _resolve_wav(req: EmotionRequest) -> Tuple[Optional[str], bool]:
    """Return (wav_path, is_temp_file), supporting base64 and legacy path modes."""
    if req.wav_base64:
        try:
            wav_bytes = base64.b64decode(req.wav_base64, validate=True)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp.write(wav_bytes)
            tmp.close()
            return tmp.name, True
        except Exception as e:
            print(f"WAV decode error: {e}")

    if req.wav_path and os.path.exists(req.wav_path):
        return req.wav_path, False

    return None, False


def _cleanup_temp_wav(wav_path: Optional[str], is_temp: bool) -> None:
    if not (is_temp and wav_path):
        return
    try:
        os.unlink(wav_path)
    except Exception as e:
        print(f"Temporary WAV cleanup error: {e}")


@app.get("/")
def root():
    return {
        "message": "Delivery Quality Service Running",
        "version": "2.0",
        "signals": ["fluency", "voice_prosody"]
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "emotion_service"}


@app.post("/predict")
def predict(req: EmotionRequest):
    wav_path, is_temp = _resolve_wav(req)
    try:
        score = predict_emotion_score(
            text=req.text,
            wav_path=wav_path,
            duration_seconds=req.duration_seconds,
        )
        return {
            "emotion_score": score,
            "delivery_score": score,
            "communication_signal": score,
        }
    finally:
        _cleanup_temp_wav(wav_path, is_temp)


@app.post("/predict_detail")
def predict_detail(req: EmotionRequest):
    """Extended endpoint with full breakdown — for debugging."""
    wav_path, is_temp = _resolve_wav(req)
    try:
        return predict_emotion_detail(
            text=req.text,
            wav_path=wav_path,
            duration_seconds=req.duration_seconds,
        )
    finally:
        _cleanup_temp_wav(wav_path, is_temp)
