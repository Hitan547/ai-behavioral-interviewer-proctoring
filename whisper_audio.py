"""
whisper_audio.py
----------------
Browser-based audio recorder + Groq Whisper transcriber.

Records audio from the candidate's browser (via streamlit-webrtc AudioFrame),
saves to a 16kHz WAV file (resampled from browser's native 48kHz),
then transcribes with Groq's Whisper API (whisper-large-v3-turbo).

No local Whisper model needed — works on any deployed server with zero GPU.
Uses GROQ_API_KEY_2 (dedicated audio key, separate from LLM key to avoid rate limits).
"""

import tempfile
import numpy as np
import threading
import os
import wave
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env early so API keys are available in every run mode.
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(str(_env_path), override=True)
    print(f"[whisper_audio] Loaded .env from: {_env_path}")
else:
    load_dotenv(override=True)
    print("[whisper_audio] No .env found, using system env vars")

# ── Sample rates ───────────────────────────────────────────────────────────
WHISPER_SR = 16000   # Groq Whisper expects 16kHz
BROWSER_SR = 48000   # WebRTC browser output is always 48kHz

# ── VAD / silence constants ────────────────────────────────────────────────
_SILENCE_RMS    = 0.003
_VAD_FRAME_MS   = 30
_VAD_RMS_THRESH = 0.004
_MIN_SPEECH_SEC = 1.5

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
    """
    arr = np.asarray(arr)
    if arr.ndim == 2:
        axis = 0 if arr.shape[0] <= 4 else 1
        arr = arr.mean(axis=axis)
    arr = arr.reshape(-1)

    if arr.dtype == np.int16:
        return arr.astype(np.float32) / 32768.0
    elif arr.dtype in (np.float32, np.float64):
        return np.clip(arr.astype(np.float32), -1.0, 1.0)
    else:
        arr = arr.astype(np.float32)
        peak = np.abs(arr).max()
        return arr / peak if peak > 0 else arr


def _resample(audio: np.ndarray, src_sr: int, tgt_sr: int) -> np.ndarray:
    """Resample float32 mono audio. Falls back to linear interp if scipy missing."""
    if src_sr == tgt_sr:
        return audio
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(tgt_sr, src_sr)
        return resample_poly(audio, tgt_sr // g, src_sr // g).astype(np.float32)
    except Exception:
        new_len = int(len(audio) * tgt_sr / src_sr)
        return np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)), audio
        ).astype(np.float32)


def _trim_silence(audio: np.ndarray, fs: int) -> np.ndarray:
    frame_len  = int(fs * _VAD_FRAME_MS / 1000)
    frames     = [audio[i:i+frame_len] for i in range(0, len(audio), frame_len)]
    speech_idx = [
        i for i, f in enumerate(frames)
        if len(f) > 0 and np.sqrt(np.mean(f ** 2)) > _VAD_RMS_THRESH
    ]
    if not speech_idx:
        return audio
    start = max(0, speech_idx[0] - 2) * frame_len
    end   = min(len(frames), speech_idx[-1] + 3) * frame_len
    return audio[start:end]


def _has_enough_speech(audio: np.ndarray, fs: int) -> bool:
    """Require consecutive speech, not just scattered loud frames."""
    frame_len = int(fs * _VAD_FRAME_MS / 1000)
    frames = [audio[i:i+frame_len] for i in range(0, len(audio), frame_len)]

    max_consecutive = 0
    current_run = 0
    for f in frames:
        if len(f) > 0 and np.sqrt(np.mean(f ** 2)) > _VAD_RMS_THRESH:
            current_run += 1
            max_consecutive = max(max_consecutive, current_run)
        else:
            current_run = 0

    min_consecutive = int(500 / _VAD_FRAME_MS)
    return max_consecutive >= min_consecutive


# ══════════════════════════════════════════════════════════════════════════
# GROQ TRANSCRIPTION
# ══════════════════════════════════════════════════════════════════════════

def _transcribe_with_groq(wav_path: str) -> str:
    """
    Send WAV file to Groq Whisper API and return transcript string.
    Uses GROQ_API_KEY_2 (dedicated audio key).
    Falls back to GROQ_API_KEY if _2 is not set.
    """
    api_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "CRITICAL: No Groq API key found.\n"
            "  Check: GROQ_API_KEY_2 or GROQ_API_KEY\n"
            "  File: .env must exist in project root\n"
            "  Try: restart app via run_system.bat which sets env vars\n"
            "  or: add GROQ_API_KEY=gsk_xxx to your .env"
        )

    from groq import Groq
    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        raise RuntimeError(
            f"Failed to create Groq client: {e}\n"
            f"  API key format: {api_key[:8] if api_key else 'EMPTY'}...\n"
            "  Key should start with 'gsk_'"
        )

    # Newer Groq SDKs expose audio transcriptions through client.audio.
    if hasattr(client, "audio") and hasattr(client.audio, "transcriptions"):
        with open(wav_path, "rb") as f:
            try:
                result = client.audio.transcriptions.create(
                    file=("audio.wav", f),
                    model="whisper-large-v3-turbo",
                    language="en",
                    response_format="text",
                )
            except Exception as api_error:
                raise RuntimeError(
                    f"Groq API call failed: {api_error}\n"
                    f"  File: {wav_path}\n"
                    "  Model: whisper-large-v3-turbo\n"
                    "  Check: API key valid? Quota remaining? Network OK?"
                )

        # response_format="text" returns the string directly in newer groq sdk
        if isinstance(result, str):
            return result.strip()
        # older SDK variants may return object wrappers
        return getattr(result, "text", str(result)).strip()

    # Compatibility fallback for older Groq SDK versions without client.audio.
    try:
        with open(wav_path, "rb") as f:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.wav", f, "audio/wav")},
                data={
                    "model": "whisper-large-v3-turbo",
                    "language": "en",
                    "response_format": "text",
                },
                timeout=60,
            )
    except Exception as api_error:
        raise RuntimeError(
            f"Groq HTTP fallback failed: {api_error}\n"
            f"  File: {wav_path}\n"
            "  Model: whisper-large-v3-turbo\n"
            "  Check: network/firewall/proxy settings"
        )

    if not resp.ok:
        raise RuntimeError(
            "Groq HTTP fallback returned error:\n"
            f"  Status: {resp.status_code}\n"
            f"  Body: {resp.text[:240]}"
        )

    # response_format=text returns plain text body.
    txt = resp.text.strip()
    if txt:
        return txt

    # Defensive parse if API returns JSON unexpectedly.
    try:
        data = resp.json()
        return str(data.get("text", "")).strip()
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API  (same interface as before — app.py needs zero changes)
# ══════════════════════════════════════════════════════════════════════════

def save_audio_frames_to_wav(frames: list, sample_rate: int = BROWSER_SR) -> str:
    """
    Convert browser audio frames → resample to 16kHz → save as WAV.

    Args:
        frames:      List of numpy arrays collected from audio receiver
        sample_rate: Source sample rate from the browser (default 48000)

    Returns:
        Path to 16kHz WAV file, or None on failure.
    """
    if not frames:
        print("[whisper_audio] save_audio_frames_to_wav: no frames received")
        return None

    try:
        chunks  = [_to_float32_mono(f) for f in frames]
        audio   = np.concatenate(chunks)
        print(f"[whisper_audio] raw audio: {len(audio)} samples @ {sample_rate}Hz  "
              f"rms={np.sqrt(np.mean(audio**2)):.5f}  max={np.abs(audio).max():.4f}")

        audio16     = _resample(audio, sample_rate, WHISPER_SR)
        audio_int16 = (audio16 * 32767).clip(-32768, 32767).astype(np.int16)
        print(f"[whisper_audio] resampled to {WHISPER_SR}Hz: {len(audio16)} samples")

        tmp      = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        with wave.open(tmp_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(WHISPER_SR)
            wf.writeframes(audio_int16.tobytes())

        print(f"[whisper_audio] WAV saved: {tmp_path}  ({os.path.getsize(tmp_path)} bytes)")
        return tmp_path

    except Exception as e:
        print(f"[whisper_audio] save_audio_frames_to_wav error: {e}")
        return None


def transcribe_wav(wav_path: str, container: dict, duration: int = 60):
    """
    Transcribe a 16kHz WAV using Groq Whisper in a background thread.
    Sets container['text'], container['done'], container['wav_path'].
    Identical interface to the old local-Whisper version — app.py unchanged.
    """
    def task():
        try:
            if not wav_path or not os.path.exists(wav_path):
                print("[whisper_audio] WAV path missing")
                container.update({"text": "", "wav_path": None,
                                  "duration": duration, "done": True})
                return

            # ── VAD check before hitting the API ──────────────────────
            import scipy.io.wavfile as wavfile
            fs, raw   = wavfile.read(wav_path)
            audio_f   = (raw.flatten().astype(np.float32) / 32768.0
                         if raw.dtype == np.int16
                         else np.clip(raw.flatten().astype(np.float32), -1.0, 1.0))

            rms = float(np.sqrt(np.mean(audio_f ** 2)))
            print(f"[whisper_audio] VAD: {len(audio_f)} samples @ {fs}Hz  rms={rms:.5f}")

            if rms < _SILENCE_RMS:
                print("[whisper_audio] silence - skipping API call")
                container.update({"text": "", "wav_path": None,
                                  "duration": duration, "done": True})
                return

            trimmed = _trim_silence(audio_f, fs)
            if not _has_enough_speech(trimmed, fs):
                print("[whisper_audio] not enough speech after VAD trim")
                container.update({"text": "", "wav_path": None,
                                  "duration": duration, "done": True})
                return

            container["wav_path"] = wav_path
            container["duration"] = duration

            # Groq API call.
            api_key_loaded = bool(os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY"))
            print("[whisper_audio] Calling Groq Whisper API...")
            print(f"[whisper_audio] API Key present: {api_key_loaded}")
            if not api_key_loaded:
                print("[whisper_audio] WARNING: No API key found before API call!")
            text = _transcribe_with_groq(wav_path)

            if text:
                normalized = text.strip().lower().rstrip(".")
                if normalized in _HALLUCINATIONS or len(text.strip()) < 8:
                    print(f"[whisper_audio] Filtered hallucination: '{text}'")
                    container.update({
                        "text": "",
                        "wav_path": None,
                        "duration": duration,
                        "done": True,
                    })
                    return

            print(f"[whisper_audio] transcript ok: '{text[:100]}{'...' if len(text) > 100 else ''}'")

            container["text"] = text
            container["done"] = True

        except Exception as e:
            print(f"[whisper_audio] transcribe_wav error: {e}")
            container.update({"text": f"[Transcription error: {e}]",
                              "wav_path": None, "duration": duration, "done": True})

    threading.Thread(target=task, daemon=True).start()


def record_answer_background(container: dict, duration: int = 60):
    """
    Legacy shim — audio now comes from the browser via WebRTC, not sounddevice.
    On Linux / any deployed server: sets done immediately (no-op).
    On Windows local dev: falls back to sounddevice for quick testing.
    """
    import platform
    if platform.system() != "Windows":
        container.update({"text": "", "wav_path": None,
                          "duration": duration, "done": True})
        return

    try:
        import sounddevice as sd
        import scipy.io.wavfile as wavfile

        def task():
            tmp_path = None
            try:
                audio = sd.rec(int(duration * WHISPER_SR), samplerate=WHISPER_SR,
                               channels=1, dtype=np.float32)
                sd.wait()
                audio = audio.flatten()

                if np.sqrt(np.mean(audio ** 2)) < _SILENCE_RMS:
                    container.update({"text": "", "wav_path": None,
                                      "duration": duration, "done": True})
                    return

                trimmed = _trim_silence(audio, WHISPER_SR)
                if not _has_enough_speech(trimmed, WHISPER_SR):
                    container.update({"text": "", "wav_path": None,
                                      "duration": duration, "done": True})
                    return

                tmp      = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_path = tmp.name
                wavfile.write(tmp_path, WHISPER_SR,
                              (trimmed * 32767).astype(np.int16))
                tmp.close()

                container["wav_path"] = tmp_path
                container["duration"] = duration
                container["text"]     = _transcribe_with_groq(tmp_path)
                container["done"]     = True

            except Exception as e:
                container.update({"text": f"[Transcription error: {e}]",
                                  "wav_path": None, "duration": duration, "done": True})
                if tmp_path and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except: pass

        threading.Thread(target=task, daemon=True).start()

    except ImportError:
        container.update({"text": "", "wav_path": None,
                          "duration": duration, "done": True})