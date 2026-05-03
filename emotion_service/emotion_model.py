"""
emotion_service/emotion_model.py
---------------------------------
Three-signal delivery quality scorer:

1. Delivery Model Score (0-10) — optional custom DistilBERT signal
                                   from transcript text
                                   Model: Hitan2004/psysense-emotion-ai
                                   enabled only with ENABLE_CUSTOM_EMOTION_MODEL=1

2. Fluency Score        (0-10) — filler words, speaking pace, completeness
                                   measured directly from Whisper transcript

3. Voice/Prosody Score  (0-10) — pitch variation, energy, silence ratio
                                   measured from raw WAV audio file

Combined:
    delivery_score = 0.34 × delivery_model + 0.33 × fluency + 0.33 × voice/prosody

Why three signals:
- Delivery model alone → can be brittle for formal interview speech
- Fluency alone        → misses voice/prosody cues
- Voice alone          → misses transcript clarity
- Combined             → robust, each signal covers the others' blind spots
"""

import sys
import os
import re
import pickle
import numpy as np

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fluency_scorer import compute_fluency_score
from voice_scorer   import compute_voice_score
# ── Paths ──────────────────────────────────────────────────────────────────
HF_MODEL = "Hitan2004/psysense-emotion-ai"
HF_CACHE_DIR = os.path.join(PROJECT_ROOT, "hf_cache")
os.makedirs(HF_CACHE_DIR, exist_ok=True)
_LOCAL_ONLY = os.getenv("HF_LOCAL_ONLY", "0") == "1"
_ENABLE_CUSTOM_MODEL = os.getenv("ENABLE_CUSTOM_EMOTION_MODEL", "0").strip() == "1"

_ENCODER_PATHS = [
    os.path.join(PROJECT_ROOT, "emotion_service", "model", "label_encoder.pkl"),
    os.path.join(PROJECT_ROOT, "model", "label_encoder.pkl"),
    os.path.join(PROJECT_ROOT, "psysense-emotion-ai", "model", "label_encoder.pkl"),
]

# ── Optionally load DistilBERT model once at startup ────────────────────────
torch = None
device = None
_model = None
_tokenizer = None
_MODEL_AVAILABLE = False

if _ENABLE_CUSTOM_MODEL:
    print("Loading optional custom delivery model (Hitan2004/psysense-emotion-ai)...")
    try:
        import torch as _torch
        from transformers import (
            DistilBertForSequenceClassification,
            DistilBertTokenizerFast,
        )

        torch = _torch
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _model = DistilBertForSequenceClassification.from_pretrained(
            HF_MODEL,
            cache_dir=HF_CACHE_DIR,
            local_files_only=_LOCAL_ONLY,
        )
        _tokenizer = DistilBertTokenizerFast.from_pretrained(
            HF_MODEL,
            cache_dir=HF_CACHE_DIR,
            local_files_only=_LOCAL_ONLY,
        )
        _model.to(device)
        _model.eval()
        _MODEL_AVAILABLE = True
        print(f"Custom delivery model loaded on {device}")
    except Exception as e:
        _MODEL_AVAILABLE = False
        print(f"Custom delivery model unavailable: {e}")
        print("Continuing with LLM/fluency/voice delivery scoring.")

    # Best-effort label-encoder load for deployment diagnostics.
    for _enc_path in _ENCODER_PATHS:
        if os.path.exists(_enc_path):
            try:
                with open(_enc_path, "rb") as f:
                    pickle.load(f)
                print(f"Label encoder found: {_enc_path}")
            except Exception as e:
                print(f"Label encoder load warning ({_enc_path}): {e}")
            break
    else:
        print(f"Label encoder not found. Tried: {_ENCODER_PATHS}")
else:
    print("Custom delivery model disabled (ENABLE_CUSTOM_EMOTION_MODEL=0).")
    print("Using production-safe delivery scoring: fluency + voice/prosody + LLM fallback.")

# Hardcoded GoEmotions 28 labels — bypasses pkl numpy version conflict
_label_names = [
    "admiration", "amusement", "anger", "annoyance", "approval",
    "caring", "confusion", "curiosity", "desire", "disappointment",
    "disapproval", "disgust", "embarrassment", "excitement", "fear",
    "gratitude", "grief", "joy", "love", "nervousness",
    "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral"
]
if _MODEL_AVAILABLE:
    print(f"Custom delivery model labels available - {len(_label_names)} labels")

# ── Chunking — must match training max_length=128 ─────────────────────────
_CHUNK_TOKENS = 110
_THRESHOLD    = 0.15

# ── Delivery label groups for optional custom model ────────────────────────
_CONFIDENCE_EMOTIONS = {
    "admiration", "approval", "excitement", "joy", "optimism",
    "pride", "gratitude", "relief", "amusement"
}
_STRESS_EMOTIONS = {
    "nervousness", "fear", "confusion", "disappointment",
    "disapproval", "annoyance", "remorse", "sadness",
    "embarrassment", "grief", "disgust", "anger"
}

_groq_client = None


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not set")
        from groq import Groq

        _groq_client = Groq(api_key=key)
    return _groq_client


def _groq_delivery_score(text: str) -> float:
    """Fallback: ask Groq to score professional delivery quality on 0-10."""
    try:
        client = _get_groq_client()
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_DELIVERY_MODEL", os.getenv("GROQ_EMOTION_MODEL", "llama-3.1-8b-instant")),
            temperature=0.1,
            max_tokens=12,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Score this interview answer's professional delivery quality from 0.0 to 10.0. "
                        "Consider communication clarity, steadiness, concise phrasing, and hesitation. "
                        "Do not infer personality, mood, mental state, age, disability, gender, or identity. "
                        "10 = clear, steady, professional delivery. "
                        "0 = very unclear, fragmented, or difficult to follow. "
                        "Reply with ONLY a single number like 6.5, nothing else.\n\n"
                        f"Answer: {text[:1000]}"
                    ),
                }
            ],
        )

        raw = (resp.choices[0].message.content or "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", raw)
        if not match:
            raise ValueError(f"No numeric score in Groq response: {raw!r}")

        score = float(match.group(0))
        return round(float(np.clip(score, 0.0, 10.0)), 2)
    except Exception as e:
        print(f"Groq delivery fallback error: {e}")
        return 5.0


def _groq_emotion_score(text: str) -> float:
    """Compatibility wrapper. Internally this is now delivery scoring."""
    return _groq_delivery_score(text)


# ── DistilBERT prediction ──────────────────────────────────────────────────
def _predict_probs(text: str) -> np.ndarray:
    if not _MODEL_AVAILABLE or _model is None or _tokenizer is None:
        raise RuntimeError("Delivery model is not available")

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
    if not _MODEL_AVAILABLE or _tokenizer is None:
        raise RuntimeError("Delivery model is not available")

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
    """Convert 28 label probabilities to a 0-10 delivery signal."""
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
    Compute combined delivery quality score (0-10).

    Combines:
    - Optional custom DistilBERT delivery model (Hitan2004/psysense-emotion-ai)
    - Fluency analysis from transcript
    - Voice/prosody signal from WAV audio

    Parameters
    ----------
    text             : Whisper transcript
    wav_path         : path to WAV file (optional)
    duration_seconds : recording length for WPM calculation

    Returns
    -------
    float  0-10 delivery quality score
    """
    if not text or not text.strip():
        return 5.0

    # Strip closing pleasantries that inflate gratitude scores
    stripped = re.sub(
        r'\b(thank you|thanks|thank you so much|thank you everyone|goodbye|bye|that\'s all|that is all|i think that\'s it|i think that is it)\b[\s\S]*$',
        '', text, flags=re.IGNORECASE
    ).strip()
    text = stripped if len(stripped.split()) >= 10 else text

    if not text:
        return 5.0

    # Signal 1 — optional DistilBERT delivery model or Groq fallback
    try:
        if _MODEL_AVAILABLE:
            probs = _predict_chunked(text)
            delivery_model_score = _probs_to_emotion_score(probs)
        else:
            print("Custom model unavailable/disabled - using LLM delivery fallback")
            delivery_model_score = _groq_delivery_score(text)
    except Exception as e:
        print(f"Delivery model scoring error: {e}")
        delivery_model_score = _groq_delivery_score(text)

    # Signal 2 — Fluency from transcript
    try:
        fluency_score = compute_fluency_score(text, duration_seconds)
    except Exception as e:
        print(f"Fluency scorer error: {e}")
        fluency_score = 5.0

    # Signal 3 — Voice/prosody from audio
    try:
        if wav_path and os.path.exists(wav_path):
            voice_score = compute_voice_score(wav_path)
        else:
            voice_score = fluency_score  # fallback to fluency if no audio
    except Exception as e:
        print(f"Voice scorer error: {e}")
        voice_score = 5.0

    # Combined — balanced delivery blend
    combined = round(
        0.34 * delivery_model_score
        + 0.33 * fluency_score
        + 0.33 * voice_score,
        2
    )

    return combined


def predict_emotion_detail(text: str, wav_path: str = None,
                           duration_seconds: int = 60) -> dict:
    """Extended version with delivery breakdown for reporting/debugging."""
    if not text or not text.strip():
        return {
            "emotion_score": 5.0,
            "delivery_score": 5.0,
            "communication_signal": 5.0,
            "emotion_model": 5.0,
            "delivery_model": 5.0,
            "fluency_score": 5.0,
            "voice_score": 5.0,
            "dominant_emotion": "delivery_fallback",
            "active_emotions": {},
            "custom_model_enabled": _ENABLE_CUSTOM_MODEL,
            "custom_model_used": _MODEL_AVAILABLE,
        }

    stripped = re.sub(
        r'\b(thank you|thanks|thank you so much|thank you everyone|goodbye|bye|that\'s all|that is all|i think that\'s it|i think that is it)\b[\s\S]*$',
        '', text, flags=re.IGNORECASE
    ).strip()
    text = stripped if len(stripped.split()) >= 10 else text

    probs = None
    try:
        if _MODEL_AVAILABLE:
            probs = _predict_chunked(text)
            delivery_model_score = _probs_to_emotion_score(probs)
            dominant = _label_names[probs.argsort()[::-1][0]]
            active = {
                _label_names[i]: round(float(probs[i]), 3)
                for i in probs.argsort()[::-1]
                if probs[i] >= _THRESHOLD
            }
        else:
            print("Custom detail model unavailable/disabled - using LLM delivery fallback")
            delivery_model_score = _groq_delivery_score(text)
            dominant = "delivery_fallback"
            active = {}
    except Exception as e:
        print(f"Delivery detail scoring error: {e}")
        delivery_model_score = _groq_delivery_score(text)
        dominant = "delivery_fallback"
        active = {}

    fluency_score = compute_fluency_score(text, duration_seconds)
    voice_score   = compute_voice_score(wav_path) if wav_path and os.path.exists(wav_path) else 5.0

    combined = round(0.34 * delivery_model_score + 0.33 * fluency_score + 0.33 * voice_score, 2)

    return {
        "emotion_score":    combined,
        "delivery_score":   combined,
        "communication_signal": combined,
        "emotion_model":    round(delivery_model_score, 2),
        "delivery_model":   round(delivery_model_score, 2),
        "fluency_score":    round(fluency_score, 2),
        "voice_score":      round(voice_score, 2),
        "dominant_emotion": dominant,
        "active_emotions":  active,
        "custom_model_enabled": _ENABLE_CUSTOM_MODEL,
        "custom_model_used": _MODEL_AVAILABLE,
    }
