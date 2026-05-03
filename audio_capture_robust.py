"""
audio_transcriber.py
---------------------
Simple, accurate audio transcription using Groq Whisper.

Design principles:
  - No LLM correction (it introduces errors, not fixes them)
  - No artificial amplification or hard clipping
  - No Deepgram fallback (one clear path = fewer failure points)
  - Keywords injected via Whisper prompt parameter (free, built-in, effective)
  - Works locally and on AWS (EC2 / Lambda with EFS / ECS)

Public API:
    build_keyword_prompt(question, vocab)          -> str
    save_webrtc_frames_to_wav(frames, sample_rate) -> Optional[str]
    save_audio_bytes_to_wav(audio_bytes)           -> Optional[str]
    transcribe_wav(wav_path, container, duration, prompt)
"""

import io
import os
import wave
import tempfile
import threading
from math import gcd
from pathlib import Path
from typing import Optional, Dict, Any

import numpy as np
from dotenv import load_dotenv

# ── Load .env (absolute path works regardless of cwd) ─────────────────────
_ENV = Path(__file__).resolve().parent / ".env"
load_dotenv(str(_ENV) if _ENV.exists() else None, override=True)

# ── Constants ─────────────────────────────────────────────────────────────
WHISPER_SR   = 16_000   # Groq Whisper expects 16 kHz
BROWSER_SR   = 48_000   # WebRTC default

_SILENCE_RMS    = 0.002  # low threshold — better to attempt than to skip
_MIN_DURATION_S = 0.4    # skip only truly tiny chunks


# ══════════════════════════════════════════════════════════════════════════
# KEYWORD PROMPT BUILDER
# Whisper's `prompt` parameter biases its vocabulary towards words you list.
# This is the simplest, most reliable way to improve technical accuracy.
# No extra API calls, no post-processing, no LLM needed.
# ══════════════════════════════════════════════════════════════════════════

def filter_vocab_for_question(
    question: str,
    full_vocab: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Filter vocabulary to only terms relevant to THIS question.

    When per-question keywords are provided (from generate_questions_with_keywords),
    this simply passes them through with a cap of 10.

    When full resume vocab is provided (fallback), it does text matching
    against the question to find relevant terms.

    Args:
        question:   The current interview question.
        full_vocab: Vocab dict with 'acronyms', 'proper_nouns', 'terms'.

    Returns:
        Filtered vocab dict with only question-relevant terms.
    """
    full_vocab = full_vocab or {}
    question_lower = (question or "").lower()

    filtered = {"acronyms": [], "proper_nouns": [], "terms": []}

    # Include any term that literally appears in the question text
    for key in ("acronyms", "proper_nouns", "terms"):
        for term in (full_vocab.get(key) or []):
            t = str(term).strip()
            if not t:
                continue
            if t.lower() in question_lower or t.lower() in set(question_lower.split()):
                filtered[key].append(t)
            # Also include terms that DON'T appear in question but are
            # pre-selected by the LLM (when using per-question keywords,
            # all terms in vocab are already question-relevant)
            elif t not in filtered[key]:
                filtered[key].append(t)

    # Cap total terms at 10
    total = []
    for key in ("acronyms", "proper_nouns", "terms"):
        total.extend(filtered[key])
    if len(total) > 10:
        filtered["terms"] = filtered["terms"][:max(0, 10 - len(filtered["acronyms"]) - len(filtered["proper_nouns"]))]
        filtered["proper_nouns"] = filtered["proper_nouns"][:max(0, 10 - len(filtered["acronyms"]))]
        filtered["acronyms"] = filtered["acronyms"][:10]

    return filtered


def build_keyword_prompt(
    question: str,
    vocab: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a Whisper prompt with ONLY question-relevant terms.

    IMPORTANT: Whisper treats the prompt as "recently spoken context".
    Listing too many terms causes Whisper to hallucinate them into the
    transcript even when the candidate never said them.

    This function:
      1. Filters vocab to only terms relevant to THIS question
      2. Limits to 10 terms max
      3. Frames as a natural sentence (not a term dump)

    Args:
        question: The interview question being answered.
        vocab:    Dict with keys 'acronyms', 'proper_nouns', 'terms'.
                  Can be full resume vocab (will be filtered) or pre-filtered.

    Returns:
        A prompt string under 500 chars.
    """
    # Filter to only question-relevant terms
    filtered = filter_vocab_for_question(question, vocab)

    # Collect all filtered terms
    terms: list[str] = []
    seen: set[str] = set()
    for key in ("acronyms", "proper_nouns", "terms"):
        for item in (filtered.get(key) or []):
            t = str(item).strip()
            if t and t.casefold() not in seen:
                seen.add(t.casefold())
                terms.append(t)

    # Build a natural context sentence
    prompt = "Technical interview answer."
    if terms:
        prompt += f" Terms that may appear: {', '.join(terms)}."

    print(f"[whisper] per-question keywords: {terms}", flush=True)
    return prompt[:500]


# ══════════════════════════════════════════════════════════════════════════
# AUDIO CONVERSION HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _to_float32_mono(arr: np.ndarray) -> np.ndarray:
    """Any WebRTC frame → 1-D float32 in [-1, 1]. No clipping, no amplification."""
    arr = np.asarray(arr)
    dtype = arr.dtype

    # Collapse stereo / planar formats to mono
    if arr.ndim == 2:
        axis = 0 if arr.shape[0] <= 4 else 1
        arr = arr.mean(axis=axis)
    arr = arr.reshape(-1)

    # Normalise integer types to [-1, 1]
    if np.issubdtype(dtype, np.integer):
        peak = float(max(abs(np.iinfo(dtype).min), np.iinfo(dtype).max))
        arr = arr.astype(np.float32) / peak
    else:
        arr = arr.astype(np.float32)
        peak = float(np.abs(arr).max())
        if peak > 1.0:           # already out-of-range float — normalise once
            arr = arr / peak

    return arr.astype(np.float32)


def _resample(audio: np.ndarray, src_sr: int, tgt_sr: int) -> np.ndarray:
    """Resample float32 mono. Uses scipy (high quality) with numpy fallback."""
    if src_sr == tgt_sr:
        return audio
    try:
        from scipy.signal import resample_poly
        g = gcd(tgt_sr, src_sr)
        return resample_poly(audio, tgt_sr // g, src_sr // g).astype(np.float32)
    except Exception:
        # Numpy linear interp — acceptable for speech, fine when scipy missing
        n = int(len(audio) * tgt_sr / src_sr)
        return np.interp(
            np.linspace(0, len(audio) - 1, n),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    """
    Normalize audio to a consistent loudness level WITHOUT clipping.

    Uses peak normalization to 90% full scale.  This is safe and preserves
    the waveform shape — unlike multiplying by 1.5 and then hard-clipping,
    which destroys the peaks where consonants live.
    """
    peak = float(np.abs(audio).max())
    if peak < 1e-9:
        return audio            # silence — leave it alone
    return (audio / peak * 0.9).astype(np.float32)


def _trim_silence(audio: np.ndarray, sr: int, threshold_rms: float = 0.005, frame_ms: int = 30) -> np.ndarray:
    """
    Strip leading and trailing silence from audio.

    Extended silence at the start/end causes Whisper to hallucinate
    (e.g. repeating phrases, inserting 'Thank you for watching', etc.).
    Keeps a small 200ms pad on each side for natural sounding edges.
    """
    frame_len = int(sr * frame_ms / 1000)
    if frame_len < 1 or len(audio) < frame_len:
        return audio

    n_frames = len(audio) // frame_len
    rms_vals = np.array([
        np.sqrt(np.mean(audio[i*frame_len:(i+1)*frame_len] ** 2))
        for i in range(n_frames)
    ])

    speech_indices = np.where(rms_vals > threshold_rms)[0]
    if len(speech_indices) == 0:
        return audio  # all silence — let downstream handle it

    # Keep 200ms padding on each side
    pad_frames = max(1, int(0.2 * sr / frame_len))
    start_frame = max(0, speech_indices[0] - pad_frames)
    end_frame = min(n_frames, speech_indices[-1] + pad_frames + 1)

    trimmed = audio[start_frame * frame_len : end_frame * frame_len]

    removed_start = start_frame * frame_len / sr
    removed_end = (len(audio) - end_frame * frame_len) / sr
    if removed_start > 0.5 or removed_end > 0.5:
        print(f"[audio] Trimmed {removed_start:.1f}s from start, {removed_end:.1f}s from end", flush=True)

    return trimmed


def _speech_enhance(audio: np.ndarray, sr: int) -> np.ndarray:
    """Optional speech enhancement for Whisper transcription.

    Testing showed that DSP filtering (high-pass + pre-emphasis) made
    transcription WORSE by distorting the frequency balance. The best results
    come from raw audio + vocabulary prompting. Browser-side noiseSuppression
    and autoGainControl (enabled in WebRTC config) are sufficient.
    """
    # No DSP — browser audio processing + vocab prompts give best results
    return audio


def _write_wav(audio: np.ndarray, sample_rate: int) -> Optional[str]:
    """
    Write float32 mono array as a 16-bit PCM WAV.

    IMPORTANT: We write at the ORIGINAL sample rate (typically 48kHz).
    Previous versions resampled to 16kHz before sending to Whisper, but this
    destroyed audio quality and produced garbage transcripts. Groq's Whisper
    API handles resampling internally and produces far better results with
    the original 48kHz audio.

    Returns the temp file path, or None if audio is too quiet / too short.
    """
    if audio is None or audio.size == 0:
        return None

    rms      = float(np.sqrt(np.mean(audio ** 2)))
    duration = len(audio) / sample_rate

    print(f"[audio] samples={len(audio)}  sr={sample_rate}  "
          f"rms={rms:.5f}  duration={duration:.2f}s", flush=True)

    if rms < _SILENCE_RMS:
        print("[audio] Silence — skipping", flush=True)
        return None

    if duration < _MIN_DURATION_S:
        print(f"[audio] Too short ({duration:.2f}s) — skipping", flush=True)
        return None

    # Processing pipeline: enhance → trim → normalize
    # NOTE: No resampling! Whisper API handles it better internally.
    audio = _speech_enhance(audio, sample_rate)
    audio = _trim_silence(audio, sample_rate)
    audio = _normalize_audio(audio)

    # Audio quality diagnostics
    final_rms = float(np.sqrt(np.mean(audio ** 2)))
    final_peak = float(np.abs(audio).max())
    final_dur = len(audio) / sample_rate
    # Estimate SNR: speech frames vs noise floor
    frame_len = int(sample_rate * 0.03)
    if frame_len > 0 and len(audio) > frame_len:
        frame_rms = np.array([
            np.sqrt(np.mean(audio[i:i+frame_len] ** 2))
            for i in range(0, len(audio) - frame_len, frame_len)
        ])
        noise_floor = float(np.percentile(frame_rms, 10))
        signal_level = float(np.percentile(frame_rms, 90))
        snr = 20 * np.log10(signal_level / max(noise_floor, 1e-10))
        speech_pct = float(np.mean(frame_rms > 0.01)) * 100
        print(f"[audio] QUALITY: rms={final_rms:.4f} peak={final_peak:.3f} "
              f"snr={snr:.1f}dB speech={speech_pct:.0f}% duration={final_dur:.1f}s",
              flush=True)

    pcm   = (audio * 32767).clip(-32768, 32767).astype(np.int16)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)  # Keep original sample rate!
        wf.writeframes(pcm.tobytes())

    # Save a debug copy in the project directory so you can listen to it
    try:
        _debug_dir = Path(__file__).resolve().parent / "debug_audio"
        _debug_dir.mkdir(exist_ok=True)
        import shutil
        _debug_path = _debug_dir / "last_recording.wav"
        shutil.copy2(tmp.name, str(_debug_path))
        print(f"[audio] DEBUG copy saved: {_debug_path}", flush=True)
    except Exception:
        pass

    print(f"[audio] WAV saved: {tmp.name}  "
          f"({os.path.getsize(tmp.name):,} bytes)", flush=True)
    return tmp.name


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC: AUDIO INPUT HELPERS
# ══════════════════════════════════════════════════════════════════════════

def save_webrtc_frames_to_wav(
    frames: list,
    sample_rate: int = BROWSER_SR,
) -> Optional[str]:
    """
    Convert a list of WebRTC audio frames (numpy arrays) to a 16 kHz WAV.

    Args:
        frames:      Frames from AudioCaptureProcessor.
        sample_rate: Browser sample rate (typically 48000).

    Returns:
        Path to WAV file, or None if silent / too short.
    """
    if not frames:
        print("[audio] No frames", flush=True)
        return None

    chunks = []
    for i, f in enumerate(frames):
        try:
            mono = _to_float32_mono(np.asarray(f))
            if mono.size > 0:
                chunks.append(mono)
        except Exception as e:
            print(f"[audio] Frame {i} error: {e}", flush=True)

    if not chunks:
        return None

    return _write_wav(np.concatenate(chunks), sample_rate)


def save_audio_bytes_to_wav(audio_bytes: bytes) -> Optional[str]:
    """
    Decode WebM / OGG / MP4 bytes from st.audio_input() to a 16 kHz WAV.

    Requires PyAV: pip install av
    On AWS: include av in requirements.txt — it's a pure-Python wheel.
    """
    if not audio_bytes:
        return None

    try:
        import av
    except ImportError:
        print("[audio] PyAV not installed: pip install av", flush=True)
        return None

    try:
        container = av.open(io.BytesIO(audio_bytes))
        streams   = [s for s in container.streams if s.type == "audio"]
        if not streams:
            print("[audio] No audio stream in bytes", flush=True)
            return None

        src_sr = streams[0].codec_context.sample_rate or BROWSER_SR
        chunks = []

        for frame in container.decode(audio=0):
            arr = frame.to_ndarray()
            fmt = frame.format.name

            if fmt == "fltp":
                mono = arr.mean(axis=0) if arr.ndim == 2 else arr.flatten()
            elif fmt in ("s16", "s16p"):
                mono = (arr.mean(axis=0) if arr.ndim == 2 else arr.flatten())
                mono = mono.astype(np.float32) / 32768.0
            elif fmt in ("s32", "s32p"):
                mono = (arr.mean(axis=0) if arr.ndim == 2 else arr.flatten())
                mono = mono.astype(np.float32) / 2_147_483_648.0
            else:
                mono = arr.flatten().astype(np.float32)
                peak = float(np.abs(mono).max())
                if peak > 1.0:
                    mono /= peak

            chunks.append(np.clip(mono, -1.0, 1.0).astype(np.float32))

        container.close()

        if not chunks:
            return None

        return _write_wav(np.concatenate(chunks), src_sr)

    except Exception as e:
        print(f"[audio] Decode error: {e}", flush=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# GROQ WHISPER
# ══════════════════════════════════════════════════════════════════════════

def _get_groq_api_key() -> Optional[str]:
    key = (os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY") or "").strip()
    return key or None


def _call_whisper(wav_path: str, prompt: str = "") -> tuple[str, Optional[str]]:
    """
    Send a WAV file to Groq Whisper large-v3 via HTTP API.

    Returns (transcript, error_message).
    error_message is None on success.
    """
    api_key = _get_groq_api_key()
    if not api_key:
        return "", "GROQ_API_KEY not set — check your .env"

    try:
        import requests
        with open(wav_path, "rb") as f:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": ("audio.wav", f, "audio/wav")},
                data={
                    "model":           "whisper-large-v3",
                    "language":        "en",
                    "response_format": "text",
                    "prompt":          prompt,
                    "temperature":     "0",
                },
                timeout=60,
            )

        if resp.ok:
            return resp.text.strip(), None

        if resp.status_code in (401, 403):
            return "", f"Groq auth error ({resp.status_code}) — check API key"
        if resp.status_code == 429:
            return "", "Groq rate limit — wait a moment and retry"
        return "", f"Groq error {resp.status_code}: {resp.text[:200]}"

    except Exception as e:
        return "", f"HTTP error: {e}"

def _llm_correct_transcript(text: str, question: str, vocab: dict) -> Optional[str]:
    """
    Use LLM to fix only acoustically-misheard words in a Whisper transcript.

    CRITICAL: This must NOT change the meaning or add content.
    Only fix words that sound similar but were transcribed wrong.
    """
    api_key = _get_groq_api_key()
    if not api_key:
        return None

    # Only pass acronyms for spelling reference — not the full vocab list
    acronyms = vocab.get("acronyms") or []
    acronyms_str = ", ".join(acronyms[:20]) if acronyms else ""

    correction_prompt = (
        "You are a verbatim transcript corrector. A speech-to-text system "
        "produced a transcript that may have some misheard words.\n\n"
        "Your job: Fix ONLY words that were clearly misheard due to audio quality. "
        "The transcript is mostly correct — make minimal changes.\n\n"
        "STRICT RULES:\n"
        "1. Only fix words where the SOUND is similar but the spelling is wrong "
        "(e.g. 'modulairty' → 'modularity', 'in friends' → 'inference')\n"
        "2. NEVER insert technical terms the candidate didn't say\n"
        "3. NEVER add sentences, clauses, or information not in the original\n"
        "4. NEVER remove content — keep everything the candidate said\n"
        "5. Keep ALL fillers: 'um', 'uh', 'like', 'you know', 'so'\n"
        "6. Keep the candidate's exact sentence structure and style\n"
        "7. If unsure whether a word is wrong, LEAVE IT as-is\n"
        "8. Return ONLY the corrected transcript, nothing else\n\n"
        f"Interview Question: {question}\n\n"
    )
    if acronyms_str:
        correction_prompt += f"Acronym spellings for reference: {acronyms_str}\n\n"
    correction_prompt += f"Transcript to correct:\n{text}\n\nCorrected transcript:"

    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": correction_prompt}],
                "temperature": 0,
                "max_tokens": 1000,
            },
            timeout=30,
        )
        if resp.ok:
            corrected = resp.json()["choices"][0]["message"]["content"].strip()
            # Sanity: correction should be similar length (within 50%)
            ratio = len(corrected) / max(len(text), 1)
            if len(corrected) > 10 and 0.5 < ratio < 1.5:
                return corrected
            print(f"[llm] Correction rejected (length ratio={ratio:.2f})", flush=True)
            return None
        print(f"[llm] API error {resp.status_code}", flush=True)
        return None
    except Exception as e:
        print(f"[llm] Correction error: {e}", flush=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC: TRANSCRIBE (background thread, same interface as before)
# ══════════════════════════════════════════════════════════════════════════

def transcribe_wav(
    wav_path: str,
    container: Dict[str, Any],
    duration: int = 60,
    prompt: str = "",
) -> None:
    """
    Transcribe a 16 kHz WAV with Groq Whisper in a background thread.

    If `prompt` is empty, it is auto-built from container["question"] and
    container["vocab"] using build_keyword_prompt().

    Writes into `container`:
        container["text"]     — transcript (empty string on failure)
        container["done"]     — True when finished
        container["error"]    — error string or None
        container["wav_path"] — wav_path on success, None on failure
        container["duration"] — echo of duration argument
    """
    def _task():
        try:
            # ── Validate file ──────────────────────────────────────────
            if not wav_path or not os.path.exists(wav_path):
                container.update({
                    "text": "", "done": True, "error": "Audio file missing",
                    "wav_path": None, "duration": duration,
                })
                return

            # ── Quick duration check ───────────────────────────────────
            try:
                import scipy.io.wavfile as wf
                fs, raw = wf.read(wav_path)
                dur = len(raw) / fs
                if dur < _MIN_DURATION_S:
                    container.update({
                        "text": "", "done": True, "wav_path": None, "duration": duration,
                        "error": "Recording too short — please speak for at least half a second.",
                    })
                    return
                print(f"[whisper] duration={dur:.1f}s", flush=True)
            except Exception:
                pass   # can't read WAV — attempt transcription anyway

            # ── Build prompt if not provided ───────────────────────────
            effective_prompt = prompt or build_keyword_prompt(
                question = container.get("question", ""),
                vocab    = container.get("vocab",    {}),
            )
            print(f"[whisper] prompt: {effective_prompt[:120]!r}", flush=True)

            # ── Transcribe ─────────────────────────────────────────────
            container["wav_path"] = wav_path
            container["duration"] = duration

            text, error = _call_whisper(wav_path, prompt=effective_prompt)

            if error:
                print(f"[whisper] Error: {error}", flush=True)
                container.update({
                    "text": "", "done": True,
                    "wav_path": None, "duration": duration, "error": error,
                })
                return

            print(f"[whisper] Raw transcript ({len(text)} chars): {text[:100]!r}", flush=True)

            # ── LLM post-correction ──────────────────────────────────
            # Whisper garbles words due to mic quality. LLaMA fixes them
            # using question context + resume vocabulary.
            question_text = container.get("question", "")
            vocab_data = container.get("vocab", {})
            if text and question_text:
                corrected = _llm_correct_transcript(text, question_text, vocab_data)
                if corrected:
                    print(f"[whisper] Corrected ({len(corrected)} chars): {corrected[:100]!r}", flush=True)
                    text = corrected

            container.update({
                "text":     text,
                "done":     True,
                "wav_path": wav_path,
                "duration": duration,
                "error":    None,
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            container.update({
                "text": "", "done": True, "wav_path": None, "duration": duration,
                "error": f"Unexpected error: {e}",
            })

    threading.Thread(target=_task, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════
# WebRTC CONFIG (unchanged — drop-in replacement for audio_capture_robust.py)
# ══════════════════════════════════════════════════════════════════════════

def get_webrtc_config_for_saas() -> Dict[str, Any]:
    ice_servers = [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {"urls": ["stun:stun1.l.google.com:19302"]},
    ]
    turn_urls = [
        url.strip()
        for url in os.getenv("WEBRTC_TURN_URLS", "").split(",")
        if url.strip()
    ]
    if turn_urls:
        turn_server = {"urls": turn_urls}
        turn_username = os.getenv("WEBRTC_TURN_USERNAME", "").strip()
        turn_password = os.getenv("WEBRTC_TURN_PASSWORD", "").strip()
        if turn_username and turn_password:
            turn_server["username"] = turn_username
            turn_server["credential"] = turn_password
        ice_servers.append(turn_server)

    return {
        "rtc_configuration": {
            "iceServers": ice_servers,
        },
        "media_stream_constraints": {
            "video": {
                "width":     {"ideal": 640,  "max": 1280},
                "height":    {"ideal": 480,  "max": 720},
                "frameRate": {"ideal": 15,   "max": 30},
            },
            "audio": {
                "echoCancellation": True,
                "noiseSuppression": True,
                "autoGainControl":  True,
            },
        },
        "sendback_audio": True,
    }
