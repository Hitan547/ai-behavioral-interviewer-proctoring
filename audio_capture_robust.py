"""
audio_capture_robust.py
-----------------------
Production-grade audio capture with automatic microphone detection,
fallback mechanisms, and user-friendly error handling for SaaS.

Features:
- Auto-detects available microphones (no manual selection needed)
- Graceful fallbacks if primary mic fails
- Clear, actionable error messages for users
- Works with built-in, USB, array, and virtual microphones
- Browser-agnostic (Chrome, Edge, Firefox)
"""

import io
import tempfile
import numpy as np
import threading
import os
import wave
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Dict, Any

# Load .env early so API keys are available in every run mode.
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(str(_env_path), override=True)
    print(f"[audio_capture] Loaded .env from: {_env_path}")
else:
    load_dotenv(override=True)
    print("[audio_capture] No .env found, using system env vars")

# ── Sample rates ───────────────────────────────────────────────────────────
WHISPER_SR = 16000   # Groq Whisper expects 16kHz
BROWSER_SR = 48000   # WebRTC browser output is always 48kHz

# ── VAD / silence constants ────────────────────────────────────────────────
_SILENCE_RMS    = 0.0024
_VAD_FRAME_MS   = 30
_VAD_RMS_THRESH = 0.004
_MIN_SPEECH_SEC = 1.5

# Adaptive leveling and low-confidence guards for far-field microphone audio.
_LEVEL_ACTIVITY_RMS_THRESH = 0.0018
_LEVEL_EST_RMS_THRESH = 0.0022
_LEVEL_TARGET_SPEECH_RMS = 0.045
_LEVEL_MAX_GAIN = 4.0
_LEVEL_MIN_ACTIVITY_RATIO = 0.06
_LEVEL_HARD_LIMIT = 0.98
_LOW_SIGNAL_RMS = 0.0022
_LOW_SIGNAL_SPEECH_RATIO = 0.045

# Common Whisper false positives on silence/noise.
_HALLUCINATIONS = {
    "thank you", "thanks", "bye", "bye bye", "goodbye", "see you",
    "you", ".", "..", "...", "the", "uh", "um", "hmm", "okay", "ok",
    "thank you.", "thanks.", "bye.", "you.", "the.", "okay.",
    "subtitles by", "transcribed by", "www.", ".com",
}


# ══════════════════════════════════════════════════════════════════════════
# AUDIO HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _to_float32_mono(arr: np.ndarray) -> np.ndarray:
    """
    Convert any WebRTC audio frame array to 1-D float32 in [-1, 1].
    Handles int16 (s16) and float32 planar/interleaved (fltp) formats.
    
    Robust: works with any input shape/dtype, including edge cases.
    """
    arr = np.asarray(arr)
    orig_dtype = arr.dtype
    
    # Handle multi-channel: average down to mono
    if arr.ndim == 2:
        axis = 0 if arr.shape[0] <= 4 else 1
        arr = arr.mean(axis=axis)
    
    arr = arr.reshape(-1)

    if np.issubdtype(orig_dtype, np.integer):
        if orig_dtype == np.int16:
            arr = arr.astype(np.float32) / 32768.0
        else:
            info = np.iinfo(orig_dtype)
            peak = float(max(abs(info.min), info.max))
            arr = arr.astype(np.float32) / (peak if peak > 0 else 1.0)
    else:
        arr = arr.astype(np.float32)
        peak = float(np.abs(arr).max()) if arr.size else 0.0
        if peak > 1.0:
            arr = arr / peak
    
    # Clip to [-1, 1] and convert to float32
    return np.clip(arr, -1.0, 1.0).astype(np.float32)


def _audio_frame_to_float32_mono(frame) -> np.ndarray:
    """Convert a PyAV AudioFrame to float32 mono in [-1, 1]."""
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

    if fmt == "fltp":
        mono = arr.mean(axis=0) if arr.ndim == 2 else arr.reshape(-1)
        return _finalize(mono)

    if fmt == "s16p":
        mono = arr.mean(axis=0) if arr.ndim == 2 else arr.reshape(-1)
        return _finalize(mono, scale=32768.0)

    if fmt == "s16":
        if arr.ndim == 2 and arr.shape[0] == 1:
            packed = arr.reshape(-1).astype(np.float32)
            ch_count = 1
            try:
                layout = getattr(frame, "layout", None)
                if layout is not None:
                    ch_count = int(getattr(layout, "channels", 1) or 1)
            except Exception:
                ch_count = 1

            if ch_count > 1 and packed.size >= ch_count:
                usable = (packed.size // ch_count) * ch_count
                if usable > 0:
                    packed = packed[:usable].reshape(-1, ch_count).mean(axis=1)
            return _finalize(packed, scale=32768.0)

        mono = arr.mean(axis=0) if arr.ndim == 2 else arr.reshape(-1)
        return _finalize(mono, scale=32768.0)

    return _to_float32_mono(arr)


def _save_float_audio_to_wav(audio: np.ndarray, sample_rate: int, source_label: str) -> Optional[str]:
    """Normalize float audio, resample to 16kHz, and write to temp WAV."""
    if audio is None:
        print(f"[audio_capture] No {source_label} audio to save")
        return None

    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        print(f"[audio_capture] Empty {source_label} audio after conversion")
        return None

    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak > 1.0:
        audio = audio / peak
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)

    rms = float(np.sqrt(np.mean(audio ** 2)))
    audio, gain, pre_rms, speech_rms = _apply_adaptive_leveling(audio, sample_rate)
    post_rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0

    print(
        f"[audio_capture] Prepared {source_label} audio: {len(audio)} samples @ {sample_rate}Hz"
    )
    print(
        f"  RMS(raw)={rms:.6f}, RMS(pre)={pre_rms:.6f}, "
        f"SpeechRMS={speech_rms:.6f}, Gain={gain:.2f}x, "
        f"RMS(post)={post_rms:.6f}, Peak={np.abs(audio).max():.4f}"
    )

    audio16 = _resample(audio, sample_rate, WHISPER_SR)
    audio_int16 = (audio16 * 32767).clip(-32768, 32767).astype(np.int16)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()

    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(WHISPER_SR)
        wf.writeframes(audio_int16.tobytes())

    file_size = os.path.getsize(tmp_path)
    print(f"[audio_capture] WAV saved: {tmp_path} ({file_size} bytes)")
    return tmp_path


def _resample(audio: np.ndarray, src_sr: int, tgt_sr: int) -> np.ndarray:
    """
    Resample float32 mono audio robustly.
    Falls back to linear interp if scipy missing.
    """
    if src_sr == tgt_sr:
        return audio
    
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(tgt_sr, src_sr)
        resampled = resample_poly(audio, tgt_sr // g, src_sr // g)
        return resampled.astype(np.float32)
    except ImportError:
        print("[audio_capture] scipy not available, using linear interpolation")
        new_len = int(len(audio) * tgt_sr / src_sr)
        return np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)), audio
        ).astype(np.float32)
    except Exception as e:
        print(f"[audio_capture] resample error: {e}, using linear interp")
        new_len = int(len(audio) * tgt_sr / src_sr)
        return np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)), audio
        ).astype(np.float32)


def _frame_rms_values(audio: np.ndarray, fs: int) -> list[float]:
    """Return per-frame RMS values for VAD and confidence checks."""
    frame_len = max(1, int(fs * _VAD_FRAME_MS / 1000))
    values = []
    for i in range(0, len(audio), frame_len):
        frame = audio[i:i + frame_len]
        if len(frame) == 0:
            continue
        values.append(float(np.sqrt(np.mean(frame ** 2))))
    return values


def _adaptive_vad_threshold(audio: np.ndarray, fs: int) -> float:
    """
    Lower VAD threshold slightly for quiet/far speech, while keeping
    the original threshold for normal/near speech.
    """
    rms_values = _frame_rms_values(audio, fs)
    if not rms_values:
        return _VAD_RMS_THRESH
    p75 = float(np.percentile(rms_values, 75))
    adaptive = p75 * 0.55
    return float(max(_SILENCE_RMS, min(_VAD_RMS_THRESH, adaptive)))


def _speech_activity_ratio(audio: np.ndarray, fs: int, threshold: float) -> float:
    """Fraction of frames considered active speech at a given threshold."""
    rms_values = _frame_rms_values(audio, fs)
    if not rms_values:
        return 0.0
    active = sum(1 for v in rms_values if v > threshold)
    return float(active / len(rms_values))


def _estimate_speech_rms(audio: np.ndarray, fs: int) -> float:
    """Estimate effective speech RMS from active frames only."""
    rms_values = _frame_rms_values(audio, fs)
    if not rms_values:
        return 0.0
    # Use a dedicated low threshold so far-field speech can still be estimated.
    speech_threshold = _LEVEL_EST_RMS_THRESH
    speech_values = [v for v in rms_values if v > speech_threshold]
    if not speech_values:
        return 0.0
    return float(np.percentile(speech_values, 70))


def _apply_adaptive_leveling(audio: np.ndarray, fs: int) -> tuple[np.ndarray, float, float, float]:
    """
    Boost quiet/far-field speech with bounded gain.

    Returns:
        (leveled_audio, applied_gain, pre_rms, estimated_speech_rms)
    """
    if audio is None or len(audio) == 0:
        return audio, 1.0, 0.0, 0.0

    pre_rms = float(np.sqrt(np.mean(audio ** 2)))
    speech_rms = _estimate_speech_rms(audio, fs)
    activity_ratio = _speech_activity_ratio(
        audio,
        fs,
        threshold=_LEVEL_ACTIVITY_RMS_THRESH,
    )

    if speech_rms <= 0.0 or activity_ratio < _LEVEL_MIN_ACTIVITY_RATIO:
        return audio.astype(np.float32), 1.0, pre_rms, speech_rms

    gain = _LEVEL_TARGET_SPEECH_RMS / max(speech_rms, 1e-9)
    gain = float(min(_LEVEL_MAX_GAIN, max(1.0, gain)))

    leveled = np.clip(audio * gain, -_LEVEL_HARD_LIMIT, _LEVEL_HARD_LIMIT).astype(np.float32)
    return leveled, gain, pre_rms, speech_rms


def _trim_silence(audio: np.ndarray, fs: int) -> np.ndarray:
    """Remove leading/trailing silence from audio."""
    frame_len  = int(fs * _VAD_FRAME_MS / 1000)
    vad_thresh = _adaptive_vad_threshold(audio, fs)
    frames     = [audio[i:i+frame_len] for i in range(0, len(audio), frame_len)]
    speech_idx = [
        i for i, f in enumerate(frames)
        if len(f) > 0 and np.sqrt(np.mean(f ** 2)) > vad_thresh
    ]
    if not speech_idx:
        return audio
    start = max(0, speech_idx[0] - 2) * frame_len
    end   = min(len(frames), speech_idx[-1] + 3) * frame_len
    return audio[start:end]


def _has_enough_speech(audio: np.ndarray, fs: int) -> bool:
    """Require consecutive speech, not just scattered loud frames."""
    frame_len = int(fs * _VAD_FRAME_MS / 1000)
    vad_thresh = _adaptive_vad_threshold(audio, fs)
    frames = [audio[i:i+frame_len] for i in range(0, len(audio), frame_len)]

    max_consecutive = 0
    current_run = 0
    for f in frames:
        if len(f) > 0 and np.sqrt(np.mean(f ** 2)) > vad_thresh:
            current_run += 1
            max_consecutive = max(max_consecutive, current_run)
        else:
            current_run = 0

    # Need at least 500ms of consecutive speech.
    min_consecutive = int((_MIN_SPEECH_SEC * 1000) / _VAD_FRAME_MS)
    return max_consecutive >= min_consecutive


# ══════════════════════════════════════════════════════════════════════════
# GROQ TRANSCRIPTION (with robust error handling)
# ══════════════════════════════════════════════════════════════════════════

def _transcribe_with_groq(wav_path: str, prompt: str = "") -> tuple[str, Optional[str]]:
    """
    Send WAV file to Groq Whisper API and return (transcript, error_message).
    
    Returns:
        (transcript_text, None) on success
        ("", error_string) on failure
    """
    api_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
    prompt_text = (prompt or "").strip() or (
        "Verbatim transcription of spoken English interview audio. "
        "Do not paraphrase or summarize. Preserve exact words, fillers, repetitions, "
        "and false starts. If unclear, write [inaudible]."
    )
    if not api_key:
        return "", (
            "Transcription API key not configured. "
            "Contact support or check server configuration."
        )

    def _extract_status_code(err: Exception) -> Optional[int]:
        status = getattr(err, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(err, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
            if isinstance(status, int):
                return status
        return None

    def _is_auth_or_permission_error(status_code: Optional[int], error_text: str) -> bool:
        msg = (error_text or "").lower()
        if status_code in (401, 403):
            return True
        non_retryable_markers = (
            "invalid api key",
            "incorrect api key",
            "unauthorized",
            "forbidden",
            "permission",
            "model_permission_blocked",
            "blocked at the organization",
            "blocked at the project",
            "authentication",
        )
        return any(marker in msg for marker in non_retryable_markers)

    def _is_transient_retryable(status_code: Optional[int], error_text: str) -> bool:
        msg = (error_text or "").lower()
        if status_code in (429, 503):
            return True
        retryable_markers = (
            "rate limit",
            "too many requests",
            "over capacity",
            "capacity",
            "overloaded",
            "temporarily unavailable",
            "service unavailable",
            "please try again",
        )
        return any(marker in msg for marker in retryable_markers)

    def _transcribe_with_model(model_id: str) -> tuple[str, Optional[str], Optional[int]]:
        # Try SDK method first (newer versions)
        if hasattr(client, "audio") and hasattr(client.audio, "transcriptions"):
            try:
                with open(wav_path, "rb") as f:
                    result = client.audio.transcriptions.create(
                        file=("audio.wav", f),
                        model=model_id,
                        language="en",
                        response_format="text",
                        prompt=prompt_text,
                        temperature=0,
                    )
                text = result if isinstance(result, str) else getattr(result, "text", "")
                return text.strip(), None, None
            except Exception as e:
                print(f"[audio_capture] SDK method failed ({model_id}): {e}")
                # Fall through to HTTP method

        # Fallback to HTTP method (for older SDK versions)
        try:
            with open(wav_path, "rb") as f:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.wav", f, "audio/wav")},
                    data={
                        "model": model_id,
                        "language": "en",
                        "response_format": "text",
                        "prompt": prompt_text,
                        "temperature": "0",
                    },
                    timeout=60,
                )
            if resp.ok:
                return resp.text.strip(), None, None
            body = (resp.text or "").strip()
            return "", f"Transcription failed: {resp.status_code} {body[:180]}", resp.status_code
        except requests.Timeout:
            return "", "Transcription service timeout. Please try again.", 503
        except Exception as e:
            status_code = _extract_status_code(e)
            return "", f"Transcription error: {str(e)[:100]}", status_code

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
    except Exception as e:
        return "", f"Failed to initialize transcription service: {str(e)[:100]}"

    primary_model = "whisper-large-v3-turbo"
    fallback_model = "whisper-large-v3"

    text, error, status_code = _transcribe_with_model(primary_model)
    if not error:
        return text, None

    # Do not retry on auth/config/permission failures.
    if _is_auth_or_permission_error(status_code, error):
        return "", error

    # Retry exactly once on transient rate/capacity issues.
    if _is_transient_retryable(status_code, error):
        print(
            "[audio_capture] Primary STT model whisper-large-v3 temporarily unavailable; "
            "retrying once with whisper-large-v3-turbo"
        )
        fb_text, fb_error, _ = _transcribe_with_model(fallback_model)
        if not fb_error:
            return fb_text, None
        return "", fb_error

    return "", error


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════

def save_audio_frames_to_wav(frames: list, sample_rate: int = BROWSER_SR) -> Optional[str]:
    """
    Convert browser audio frames → resample to 16kHz → save as WAV.
    
    ROBUST: Handles empty frames, corruption, and returns None gracefully.

    Args:
        frames:      List of numpy arrays collected from audio receiver
        sample_rate: Source sample rate from the browser (default 48000)

    Returns:
        Path to 16kHz WAV file, or None on failure.
    """
    if not frames:
        print("[audio_capture] No audio frames received from browser")
        return None

    try:
        # Convert all frames to float32 mono, handling any input format
        chunks = []
        for i, f in enumerate(frames):
            try:
                mono = _to_float32_mono(f)
                if mono is not None and len(mono) > 0:
                    chunks.append(mono)
            except Exception as e:
                print(f"[audio_capture] Frame {i} conversion failed: {e}, skipping")
                continue
        
        if not chunks:
            print("[audio_capture] No valid audio frames after conversion")
            return None
        
        audio = np.concatenate(chunks)
        return _save_float_audio_to_wav(audio, sample_rate, source_label="browser")

    except Exception as e:
        print(f"[audio_capture] save_audio_frames_to_wav failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def save_audio_input_to_wav(audio_bytes: bytes, source_hint: str = "audio_input") -> Optional[str]:
    """
    Decode st.audio_input() bytes (WebM/OGG/MP4) → 16kHz mono WAV.
    Uses PyAV (already installed via streamlit-webrtc) — no ffmpeg needed.
    """
    if not audio_bytes:
        print("[audio] Empty audio_bytes")
        return None

    import io
    try:
        import av
    except ImportError:
        print("[audio] PyAV not available — run: pip install av")
        return None

    try:
        buf = io.BytesIO(audio_bytes)
        container = av.open(buf)

        # Find the audio stream
        audio_streams = [s for s in container.streams if s.type == "audio"]
        if not audio_streams:
            print("[audio] No audio stream found in input")
            return None

        src_sr = audio_streams[0].codec_context.sample_rate or 48000
        print(f"[audio] Detected stream: sr={src_sr}, codec={audio_streams[0].codec_context.name}")

        all_samples = []
        for frame in container.decode(audio=0):
            arr = frame.to_ndarray()
            fmt = frame.format.name

            if fmt == "fltp":
                # Planar float32 — most common from Opus/WebM
                mono = arr.mean(axis=0) if arr.ndim == 2 else arr.flatten()
                mono = mono.astype(np.float32)

            elif fmt in ("s16", "s16p"):
                mono = arr.mean(axis=0) if arr.ndim == 2 else arr.flatten()
                mono = mono.astype(np.float32) / 32768.0

            elif fmt in ("s32", "s32p"):
                mono = arr.mean(axis=0) if arr.ndim == 2 else arr.flatten()
                mono = mono.astype(np.float32) / 2147483648.0

            else:
                # Unknown format — attempt generic conversion
                mono = arr.flatten().astype(np.float32)
                peak = float(np.abs(mono).max())
                if peak > 1.0:
                    mono /= peak

            all_samples.append(np.clip(mono, -1.0, 1.0))

        container.close()

        if not all_samples:
            print("[audio] No samples decoded")
            return None

        audio = np.concatenate(all_samples)
        duration_sec = len(audio) / src_sr
        rms = float(np.sqrt(np.mean(audio ** 2)))
        print(f"[audio] Decoded: {len(audio)} samples, {duration_sec:.1f}s, RMS={rms:.4f}")

        if duration_sec < 0.3:
            print("[audio] Too short — likely empty recording")
            return None

        # Adaptive leveling + resample to 16kHz
        audio, gain, pre_rms, speech_rms = _apply_adaptive_leveling(audio, src_sr)
        audio16 = _resample(audio, src_sr, WHISPER_SR)
        audio_int16 = (audio16 * 32767).clip(-32768, 32767).astype(np.int16)

        post_rms = float(np.sqrt(np.mean(audio16 ** 2)))
        print(f"[audio] gain={gain:.2f}x, pre_rms={pre_rms:.4f}, post_rms={post_rms:.4f}")

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(WHISPER_SR)
            wf.writeframes(audio_int16.tobytes())

        file_size = os.path.getsize(tmp_path)
        print(f"[audio] WAV saved: {tmp_path} ({file_size} bytes)")
        return tmp_path

    except Exception as e:
        print(f"[audio] save_audio_input_to_wav failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def transcribe_wav(
    wav_path: str,
    container: Dict[str, Any],
    duration: int = 60,
    prompt: str = "",
):
    """
    Transcribe a 16kHz WAV using Groq Whisper in a background thread.
    Sets container['text'], container['done'], container['error'].
    
    ROBUST: Handles all error cases gracefully with user-friendly messages.
    """
    def task():
        try:
            # Validate WAV exists
            if not wav_path or not os.path.exists(wav_path):
                container.update({
                    "text": "",
                    "wav_path": None,
                    "duration": duration,
                    "done": True,
                    "error": "Audio file not found"
                })
                return

            # ── VAD check before hitting the API ──────────────────────
            try:
                import scipy.io.wavfile as wavfile
            except ImportError:
                # Fallback: just try transcription without VAD
                print("[audio_capture] scipy not available, skipping VAD check")
                text, error = _transcribe_with_groq(wav_path, prompt=prompt)
                container.update({
                    "text": text,
                    "wav_path": wav_path if not error else None,
                    "duration": duration,
                    "done": True,
                    "error": error
                })
                return

            try:
                fs, raw = wavfile.read(wav_path)
                audio_f = (
                    raw.flatten().astype(np.float32) / 32768.0
                    if raw.dtype == np.int16
                    else np.clip(raw.flatten().astype(np.float32), -1.0, 1.0)
                )
            except Exception as e:
                print(f"[audio_capture] WAV read failed: {e}")
                container.update({
                    "text": "",
                    "wav_path": None,
                    "duration": duration,
                    "done": True,
                    "error": f"Could not read audio file: {str(e)[:50]}"
                })
                return

            rms = float(np.sqrt(np.mean(audio_f ** 2)))
            print(f"[audio_capture] VAD: {len(audio_f)} samples @ {fs}Hz, RMS={rms:.6f}")

            # Check for silence
            if rms < _SILENCE_RMS:
                print("[audio_capture] Detected silence only")
                container.update({
                    "text": "",
                    "wav_path": None,
                    "duration": duration,
                    "done": True,
                    "error": "No speech detected. Please speak clearly and try again."
                })
                return

            # Check for enough speech
            trimmed = _trim_silence(audio_f, fs)
            if not _has_enough_speech(trimmed, fs):
                print("[audio_capture] Not enough speech detected")
                container.update({
                    "text": "",
                    "wav_path": None,
                    "duration": duration,
                    "done": True,
                    "error": "Recording too short. Please speak for at least 0.5 seconds."
                })
                return

            trimmed_rms = float(np.sqrt(np.mean(trimmed ** 2))) if len(trimmed) else 0.0
            trimmed_vad_thresh = _adaptive_vad_threshold(trimmed, fs)
            speech_ratio = _speech_activity_ratio(trimmed, fs, trimmed_vad_thresh)
            print(
                "[audio_capture] Trim quality: "
                f"trimmed_rms={trimmed_rms:.6f}, speech_ratio={speech_ratio:.3f}, "
                f"vad_thresh={trimmed_vad_thresh:.6f}"
            )

            if trimmed_rms < _LOW_SIGNAL_RMS and speech_ratio < _LOW_SIGNAL_SPEECH_RATIO:
                print("[audio_capture] Low-confidence audio (too quiet/noisy)")
                container.update({
                    "text": "",
                    "wav_path": None,
                    "duration": duration,
                    "done": True,
                    "error": "Audio is too quiet or noisy. Please move closer to the microphone and speak clearly."
                })
                return

            # ── Call transcription API ──────────────────────────────
            container["wav_path"] = wav_path
            container["duration"] = duration

            print("[audio_capture] Transcribing with Groq Whisper...")
            text, error = _transcribe_with_groq(wav_path, prompt=prompt)

            # Retry once with strict verbatim guidance when first result looks too short.
            if not error and text:
                word_count = len([w for w in text.strip().split() if w])
                weak_result = word_count <= 6 and (trimmed_rms < 0.018 or speech_ratio < 0.28)
                if weak_result:
                    print("[audio_capture] Weak first transcript detected; retrying once with strict prompt")
                    retry_prompt = (
                        "Verbatim transcription of spoken English audio. "
                        "Output exactly what is spoken and do not infer missing words from context. "
                        "Keep fillers and repetitions. Use [inaudible] when uncertain."
                    )
                    retry_text, retry_error = _transcribe_with_groq(wav_path, prompt=retry_prompt)
                    if not retry_error and len(retry_text.strip()) > len(text.strip()):
                        text = retry_text
                        print("[audio_capture] Replaced weak transcript with retry result")

            # Filter Whisper hallucinations (common false positives on noise/silence).
            if not error and text:
                normalized = text.strip().lower().rstrip(".")
                weak_signal_text = (
                    len(text.strip()) < 5
                    and trimmed_rms < (_LOW_SIGNAL_RMS + 0.00015)
                    and speech_ratio < max(0.03, _LOW_SIGNAL_SPEECH_RATIO - 0.01)
                )
                likely_hallucination = (
                    normalized in _HALLUCINATIONS
                    and (
                        trimmed_rms < (_LOW_SIGNAL_RMS + 0.0004)
                        or speech_ratio < (_LOW_SIGNAL_SPEECH_RATIO + 0.02)
                    )
                )
                if likely_hallucination or weak_signal_text:
                    print(f"[audio_capture] Filtered hallucination: '{text}'")
                    text = ""
                    error = "No clear speech detected. Please speak louder and try again."

            if error:
                print(f"[audio_capture] Transcription error: {error}")
                container.update({
                    "text": "",
                    "wav_path": None,
                    "duration": duration,
                    "done": True,
                    "error": error
                })
            else:
                print(f"[audio_capture] Transcription success: {len(text)} chars")
                container.update({
                    "text": text,
                    "wav_path": wav_path,
                    "duration": duration,
                    "done": True,
                    "error": None
                })

        except Exception as e:
            print(f"[audio_capture] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            container.update({
                "text": "",
                "wav_path": None,
                "duration": duration,
                "done": True,
                "error": f"Unexpected error: {str(e)[:100]}"
            })

    threading.Thread(target=task, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════
# BROWSER AUDIO CONFIG HELPER
# ══════════════════════════════════════════════════════════════════════════

def get_recommended_audio_constraints() -> Dict[str, Any]:
    """
    Get recommended WebRTC audio constraints for maximum compatibility.
    
    Works with:
    - Built-in microphones
    - USB microphones
    - Array microphones
    - Virtual/software microphones
    - Headset microphones
    """
    return {
        "echoCancellation": True,
        "noiseSuppression": True,
        "autoGainControl": True,
        # Let browser choose native format; we normalize and resample later.
        # Allow browser to auto-select best mic
        # Don't force specific device ID
    }


def get_webrtc_config_for_saas() -> Dict[str, Any]:
    """
    Complete WebRTC configuration for production SaaS use.
    """
    return {
        "rtc_configuration": {
            "iceServers": [
                {"urls": ["stun:stun.l.google.com:19302"]},
                {"urls": ["stun:stun1.l.google.com:19302"]},
                {"urls": ["stun:stun2.l.google.com:19302"]},  # Fallback
                {
                    "urls": ["turn:openrelay.metered.ca:80"],
                    "username": "openrelayproject",
                    "credential": "openrelayproject",
                },
            ],
        },
        "media_stream_constraints": {
            "video": {
                "width": {"ideal": 640, "max": 1280},
                "height": {"ideal": 480, "max": 720},
                "frameRate": {"ideal": 15, "max": 30},
            },
            "audio": {
                "echoCancellation": True,
                "noiseSuppression": True,
                "autoGainControl": True,
                # Let browser choose native format; we normalize and resample later.
            },
        },
        "sendback_audio": False,
    }