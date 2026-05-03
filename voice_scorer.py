"""
voice_scorer.py
---------------
Measures voice confidence directly from the WAV audio file.
Requires: pip install librosa

Signals:
1. Voice energy     — how strongly candidate is speaking
2. Pitch variation  — monotone = nervous, varied = engaged and confident
3. Silence ratio    — too many pauses = hesitant and uncertain
4. Speech density   — how much of the recording has actual speech
"""

import numpy as np
import os

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    print("[WARNING] librosa not installed. Run: pip install librosa")
    print("          Voice scoring will return neutral 5.0 until installed.")


def compute_voice_score(wav_path: str) -> float:
    """
    Compute voice confidence score (0-10) from a WAV file.

    Parameters
    ----------
    wav_path : str   Path to the WAV file from whisper_audio.py

    Returns
    -------
    float  Voice score 0-10
           0-3  = weak voice (quiet, monotone, many pauses)
           4-6  = average (moderate energy, some variation)
           7-10 = confident (strong voice, good variation, minimal silence)
    """
    if not LIBROSA_AVAILABLE:
        return 5.0   # neutral fallback if librosa not installed

    if not wav_path:
        print(f"Voice scorer: wav_path is None — returning 5.0")
        return 5.0
    if not os.path.exists(wav_path):
        print(f"Voice scorer: file not found at {wav_path} — returning 5.0")
        return 5.0
    print(f"Voice scorer: loading {wav_path}")

    try:
        # Load audio at 16kHz (matches Whisper recording rate)
        y, sr = librosa.load(wav_path, sr=16000, mono=True)

        if len(y) < sr * 1:   # less than 1 second of audio
            return 5.0

        # ── Signal 1: Voice energy ────────────────────────────────────────
        # RMS energy — how loud/strong the voice is
        rms        = librosa.feature.rms(y=y, frame_length=512, hop_length=256)[0]
        avg_rms    = float(np.mean(rms))
        max_rms    = float(np.max(rms))

        # Scale: typical interview voice RMS is 0.02-0.08
        # Quiet/nervous < 0.02, Strong/confident > 0.05
        energy_score = min(avg_rms * 300, 10.0)

        # ── Signal 2: Pitch variation ─────────────────────────────────────
        # Monotone delivery = nervous or disengaged
        # Varied pitch = engaged and confident
        try:
            pitches, magnitudes = librosa.piptrack(
                y=y, sr=sr,
                fmin=80,    # human voice min frequency
                fmax=400    # human voice max frequency
            )
            # Only consider frames with significant magnitude
            strong_mask   = magnitudes > np.percentile(magnitudes, 60)
            pitch_values  = pitches[strong_mask]
            pitch_values  = pitch_values[pitch_values > 0]   # remove zeros

            if len(pitch_values) > 10:
                pitch_std = float(np.std(pitch_values))
                # Higher std = more pitch variation = more confident/engaged
                # Typical range: 20-80 Hz std for good speakers
                pitch_score = min(pitch_std / 15.0, 10.0)
            else:
                pitch_score = 5.0   # not enough pitch data
        except Exception:
            pitch_score = 5.0

        # ── Signal 3: Silence ratio ───────────────────────────────────────
        # Long pauses and hesitations = uncertainty
        silence_threshold = 0.008   # frames below this are silence
        silence_frames    = np.sum(np.abs(y) < silence_threshold)
        silence_ratio     = silence_frames / len(y)

        # 0-20% silence = natural pauses = good (score 10)
        # 20-40% silence = some hesitation (score 6)
        # 40%+ silence = very hesitant (score 2)
        if silence_ratio <= 0.20:
            silence_score = 10.0
        elif silence_ratio <= 0.35:
            silence_score = 6.0
        elif silence_ratio <= 0.50:
            silence_score = 3.0
        else:
            silence_score = 1.0

        # ── Signal 4: Speech density ──────────────────────────────────────
        # How consistent is the speech — are there long dead zones?
        rms_binary    = (rms > np.percentile(rms, 25)).astype(int)
        # Count transitions from speech to silence
        transitions   = np.sum(np.abs(np.diff(rms_binary)))
        # Many transitions = choppy, stop-start delivery
        density_score = max(0.0, 10.0 - (transitions / max(len(rms), 1) * 20))

        # ── Weighted combination ──────────────────────────────────────────
        final = (
            0.35 * energy_score
            + 0.30 * pitch_score
            + 0.25 * silence_score
            + 0.10 * density_score
        )

        print(f"Voice scorer: energy={energy_score:.2f} pitch={pitch_score:.2f} silence={silence_score:.2f} density={density_score:.2f} final={final:.2f}")
        return round(min(float(final), 10.0), 2)

    except Exception as e:
        print(f"Voice scoring error: {e}")
        return 5.0   # neutral fallback on any error


def get_voice_breakdown(wav_path: str) -> dict:
    """
    Detailed breakdown for debugging or future coaching display.
    """
    if not LIBROSA_AVAILABLE or not wav_path or not os.path.exists(wav_path):
        return {"voice_score": 5.0, "available": False}

    score = compute_voice_score(wav_path)
    return {
        "voice_score": score,
        "available":   True,
        "wav_path":    wav_path
    }