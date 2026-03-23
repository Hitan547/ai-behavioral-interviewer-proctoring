"""
emotion_service/emotion_model.py
---------------------------------
Three-signal speech quality scorer:

1. Emotion Model Score  (0-10) — custom DistilBERT trained on GoEmotions
                                   detects pride, confidence, nervousness etc
                                   from transcript text
                                   Model: Hitan2004/psysense-emotion-ai

2. Fluency Score        (0-10) — filler words, speaking pace, completeness
                                   measured directly from Whisper transcript

3. Voice Score          (0-10) — pitch variation, energy, silence ratio
                                   measured from raw WAV audio file

Combined:
    speech_score = 0.34 × emotion + 0.33 × fluency + 0.33 × voice

Why three signals:
- Emotion model alone → always neutral for formal speech (domain mismatch)
- Fluency alone       → misses delivery confidence (text only)
- Voice alone         → misses content quality (audio only)
- Combined            → robust, each signal covers the others' blind spots
"""

import sys
import os
import torch
import pickle
import numpy as np

from transformers import (
    DistilBertForSequenceClassification,
    DistilBertTokenizerFast,
)

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fluency_scorer import compute_fluency_score
from voice_scorer   import compute_voice_score

# ── Paths ──────────────────────────────────────────────────────────────────
HF_MODEL = "Hitan2004/psysense-emotion-ai"

_ENCODER_PATHS = [
    os.path.join(PROJECT_ROOT, "emotion_service", "model", "label_encoder.pkl"),
    os.path.join(PROJECT_ROOT, "model", "label_encoder.pkl"),
    os.path.join(PROJECT_ROOT, "psysense-emotion-ai", "model", "label_encoder.pkl"),
]

def _find_encoder():
    for p in _ENCODER_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"label_encoder.pkl not found. Tried: {_ENCODER_PATHS}")

# ── Load DistilBERT model once at startup ──────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("Loading emotion model (Hitan2004/psysense-emotion-ai)...")
_model     = DistilBertForSequenceClassification.from_pretrained(HF_MODEL)
_tokenizer = DistilBertTokenizerFast.from_pretrained(HF_MODEL)
_model.to(device)
_model.eval()

with open(_find_encoder(), "rb") as f:
    _mlb = pickle.load(f)

# Hardcoded GoEmotions 28 labels — bypasses pkl numpy version conflict
_label_names = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral"
]
print(f"✅ Emotion model loaded — {len(_label_names)} labels")

# ── Chunking — must match training max_length=128 ─────────────────────────
_CHUNK_TOKENS = 110
_THRESHOLD    = 0.15

# ── Behavioral emotion groups ──────────────────────────────────────────────
_CONFIDENCE_EMOTIONS = {
    "admiration", "approval", "excitement", "joy", "optimism",
    "pride", "gratitude", "relief", "amusement"
}
_STRESS_EMOTIONS = {
    "nervousness", "fear", "confusion", "disappointment",
    "disapproval", "annoyance", "remorse", "sadness",
    "embarrassment", "grief", "disgust", "anger"
}


# ── DistilBERT prediction ──────────────────────────────────────────────────
def _predict_probs(text: str) -> np.ndarray:
    inputs = _tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=128,
    ).to(device)
    with torch.no_grad():
        logits = _model(**inputs).logits
    return torch.sigmoid(logits)[0].cpu().numpy()


def _predict_chunked(text: str) -> np.ndarray:
    token_ids = _tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= _CHUNK_TOKENS:
        return _predict_probs(text)
    chunk_probs = []
    for start in range(0, len(token_ids), _CHUNK_TOKENS):
        chunk_text = _tokenizer.decode(
            token_ids[start:start + _CHUNK_TOKENS],
            skip_special_tokens=True
        )
        if chunk_text.strip():
            chunk_probs.append(_predict_probs(chunk_text))
    return np.mean(chunk_probs, axis=0) if chunk_probs else np.zeros(len(_label_names))


def _probs_to_emotion_score(probs: np.ndarray) -> float:
    """Convert 28 emotion probabilities to 0-10 behavioral score."""
    label_prob = {label: float(probs[i]) for i, label in enumerate(_label_names)}

    confidence_signal = sum(
        label_prob.get(e, 0.0) for e in _CONFIDENCE_EMOTIONS
        if label_prob.get(e, 0.0) >= _THRESHOLD
    )
    stress_signal = sum(
        label_prob.get(e, 0.0) for e in _STRESS_EMOTIONS
        if label_prob.get(e, 0.0) >= _THRESHOLD
    )

    raw = 5.0 + (confidence_signal - stress_signal) * 6.0
    return round(float(np.clip(raw, 0.0, 10.0)), 2)


# ── Public API ─────────────────────────────────────────────────────────────
def predict_emotion_score(text: str, wav_path: str = None,
                          duration_seconds: int = 60) -> float:
    """
    Compute combined speech quality score (0-10).

    Combines:
    - Your custom DistilBERT emotion model (Hitan2004/psysense-emotion-ai)
    - Fluency analysis from transcript
    - Voice confidence from WAV audio

    Parameters
    ----------
    text             : Whisper transcript
    wav_path         : path to WAV file (optional)
    duration_seconds : recording length for WPM calculation

    Returns
    -------
    float  0-10 speech quality score
    """
    if not text or not text.strip():
        return 5.0

    # Strip closing pleasantries that inflate gratitude scores
    import re
    stripped = re.sub(
        r'\b(thank you|thanks|thank you so much|thank you everyone|goodbye|bye|that\'s all|that is all|i think that\'s it|i think that is it)\b[\s\S]*$',
        '', text, flags=re.IGNORECASE
    ).strip()
    text = stripped if len(stripped.split()) >= 10 else text

    if not text:
        return 5.0

    # Signal 1 — Your DistilBERT emotion model
    try:
        probs         = _predict_chunked(text)
        emotion_score = _probs_to_emotion_score(probs)
    except Exception as e:
        print(f"Emotion model error: {e}")
        emotion_score = 5.0

    # Signal 2 — Fluency from transcript
    try:
        fluency_score = compute_fluency_score(text, duration_seconds)
    except Exception as e:
        print(f"Fluency scorer error: {e}")
        fluency_score = 5.0

    # Signal 3 — Voice confidence from audio
    try:
        if wav_path and os.path.exists(wav_path):
            voice_score = compute_voice_score(wav_path)
        else:
            voice_score = fluency_score  # fallback to fluency if no audio
    except Exception as e:
        print(f"Voice scorer error: {e}")
        voice_score = 5.0

    # Combined — all three weighted equally
    combined = round(
        0.34 * emotion_score
        + 0.33 * fluency_score
        + 0.33 * voice_score,
        2
    )

    return combined


def predict_emotion_detail(text: str, wav_path: str = None,
                           duration_seconds: int = 60) -> dict:
    """Extended version with full breakdown for debugging."""
    if not text or not text.strip():
        return {"emotion_score": 5.0}

    import re
    stripped = re.sub(
        r'\b(thank you|thanks|thank you so much|thank you everyone|goodbye|bye|that\'s all|that is all|i think that\'s it|i think that is it)\b[\s\S]*$',
        '', text, flags=re.IGNORECASE
    ).strip()
    text = stripped if len(stripped.split()) >= 10 else text

    try:
        probs         = _predict_chunked(text)
        emotion_score = _probs_to_emotion_score(probs)
        dominant      = _label_names[probs.argsort()[::-1][0]]
        active        = {
            _label_names[i]: round(float(probs[i]), 3)
            for i in probs.argsort()[::-1]
            if probs[i] >= _THRESHOLD
        }
    except Exception:
        emotion_score = 5.0
        dominant      = "neutral"
        active        = {}

    fluency_score = compute_fluency_score(text, duration_seconds)
    voice_score   = compute_voice_score(wav_path) if wav_path and os.path.exists(wav_path) else 5.0

    combined = round(0.34 * emotion_score + 0.33 * fluency_score + 0.33 * voice_score, 2)

    return {
        "emotion_score":    combined,
        "emotion_model":    round(emotion_score, 2),
        "fluency_score":    round(fluency_score, 2),
        "voice_score":      round(voice_score, 2),
        "dominant_emotion": dominant,
        "active_emotions":  active,
    }