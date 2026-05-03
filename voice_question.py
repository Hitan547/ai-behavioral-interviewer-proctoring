"""
voice_question.py
-----------------
Speaks the interview question to the candidate using human-quality TTS.

Strategy (priority order):
  1. Groq Orpheus TTS (server-side) → generates WAV via HTTP API → plays in browser
     - Human-quality voice, works on AWS, Cloudflare, any deployment
     - Uses same GROQ_API_KEY you already have
     - HTTP-based — works with ANY groq SDK version
  2. Web Speech API (client-side fallback) → browser's built-in TTS
     - Robotic but guaranteed to work even if Groq is down

Usage in demo_app.py:
    from voice_question import speak_question
    speak_question(question_text)
"""

import os
import base64
import json

from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_HERE, ".env"), override=False)


# ── Config ─────────────────────────────────────────────────────────────────

_TTS_MODEL = "canopylabs/orpheus-v1-english"
_TTS_VOICE = os.getenv("TTS_VOICE", "diana")   # diana = calm professional female
_TTS_API_URL = "https://api.groq.com/openai/v1/audio/speech"


def _get_groq_api_key() -> str:
    """Get Groq API key from environment."""
    return (os.environ.get("GROQ_API_KEY_2")
            or os.environ.get("GROQ_API_KEY") or "").strip()


# ── Groq Orpheus TTS via HTTP (works with any SDK version) ─────────────────

def _fix_wav_header(wav_bytes: bytes) -> bytes:
    """
    Re-wrap WAV bytes with a correct header.

    Groq Orpheus returns WAV files with nframes=0x7FFFFFFF (max int32),
    which causes browser <audio> elements to fail playback. This reads
    the raw PCM data and writes a proper header with correct frame count.
    """
    import io
    import struct
    import wave

    try:
        # Read the raw audio data from the (possibly corrupt) WAV
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            params = wf.getparams()
            raw_data = wf.readframes(params.nframes)

        # Calculate actual frame count from data size
        bytes_per_frame = params.nchannels * params.sampwidth
        actual_frames = len(raw_data) // bytes_per_frame if bytes_per_frame > 0 else 0

        # Write a clean WAV with correct header
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(params.nchannels)
            wf.setsampwidth(params.sampwidth)
            wf.setframerate(params.framerate)
            wf.writeframes(raw_data[:actual_frames * bytes_per_frame])

        fixed = out.getvalue()
        return fixed

    except Exception as e:
        print(f"[TTS] WAV header fix failed: {e} — using original", flush=True)
        return wav_bytes

def _generate_speech_audio(text: str) -> bytes:
    """
    Generate WAV audio bytes from text using Groq Orpheus TTS HTTP API.
    Returns raw WAV bytes or empty bytes on failure.
    """
    api_key = _get_groq_api_key()
    if not api_key:
        print("[TTS] GROQ_API_KEY not set — skipping Orpheus TTS", flush=True)
        return b""

    try:
        import requests

        # Add calm vocal direction for professional interview context
        tts_input = f"[calm] {text}"

        resp = requests.post(
            _TTS_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _TTS_MODEL,
                "voice": _TTS_VOICE,
                "input": tts_input,
                "response_format": "wav",
            },
            timeout=15,
        )

        if resp.status_code != 200:
            print(
                f"[TTS] Groq API error {resp.status_code}: "
                f"{resp.text[:200]}",
                flush=True,
            )
            return b""

        audio_bytes = resp.content

        # Groq Orpheus returns WAV with corrupt header (frames=0x7FFFFFFF).
        # Re-wrap with correct header so browser <audio> element can play it.
        audio_bytes = _fix_wav_header(audio_bytes)

        print(
            f"[TTS] Orpheus generated {len(audio_bytes):,} bytes "
            f"(voice={_TTS_VOICE})",
            flush=True,
        )
        return audio_bytes

    except Exception as e:
        print(f"[TTS] Orpheus TTS failed: {e}", flush=True)
        return b""


def speak_question_groq(text: str) -> bool:
    """
    Generate human-quality audio with Groq Orpheus and inject an <audio>
    tag into the browser via st.components.v1.html.

    Returns True if audio was successfully generated and injected.
    """
    audio_bytes = _generate_speech_audio(text)
    if not audio_bytes:
        return False

    try:
        import streamlit.components.v1 as components

        # Base64-encode the WAV for embedding in an HTML audio element
        b64_audio = base64.b64encode(audio_bytes).decode("ascii")

        html = f"""
        <audio autoplay style="display:none">
            <source src="data:audio/wav;base64,{b64_audio}" type="audio/wav">
        </audio>
        <script>
        (function() {{
            var audio = document.querySelector('audio');
            if (audio) {{
                audio.volume = 1.0;
                var playPromise = audio.play();
                if (playPromise !== undefined) {{
                    playPromise.catch(function(err) {{
                        console.log('[PsySense TTS] Autoplay blocked:', err);
                    }});
                }}
            }}
        }})();
        </script>
        """

        components.html(html, height=0, scrolling=False)
        return True

    except Exception as e:
        print(f"[TTS] Browser injection failed: {e}", flush=True)
        return False


# ── Web Speech API fallback (robotic but guaranteed) ──────────────────────

def speak_question_browser(text: str):
    """
    Fallback: injects a Web Speech API utterance into the browser.
    Robotic voice but works even if Groq TTS is down.
    """
    import streamlit.components.v1 as components

    js_safe_text = json.dumps(text)

    html = f"""
    <script>
    (function () {{
        window.speechSynthesis.cancel();

        var text = {js_safe_text};

        function _speak() {{
            var utterance = new SpeechSynthesisUtterance(text);
            utterance.lang   = 'en-US';
            utterance.rate   = 0.92;
            utterance.pitch  = 1.0;
            utterance.volume = 1.0;

            var voices = window.speechSynthesis.getVoices();
            var preferred = voices.find(function(v) {{
                return v.lang.startsWith('en') && !v.name.toLowerCase().includes('zira');
            }});
            if (preferred) utterance.voice = preferred;

            window.speechSynthesis.speak(utterance);
        }}

        if (window.speechSynthesis.getVoices().length > 0) {{
            _speak();
        }} else {{
            window.speechSynthesis.onvoiceschanged = function () {{
                window.speechSynthesis.onvoiceschanged = null;
                _speak();
            }};
            setTimeout(function () {{
                if (window.speechSynthesis.pending || window.speechSynthesis.speaking) return;
                _speak();
            }}, 500);
        }}
    }})();
    </script>
    """

    components.html(html, height=0, scrolling=False)


# ── Unified entry point ────────────────────────────────────────────────────

def speak_question(text: str):
    """
    Speak a question to the candidate.

    1. Try Groq Orpheus TTS (human-quality voice) — works on AWS
    2. Fall back to Web Speech API (robotic) if Groq fails
    """
    if speak_question_groq(text):
        return

    print("[TTS] Falling back to Web Speech API", flush=True)
    speak_question_browser(text)