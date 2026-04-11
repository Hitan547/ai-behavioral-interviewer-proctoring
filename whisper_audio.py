"""
whisper_audio.py
----------------
Browser-based audio recorder + local Whisper transcriber.

Records audio from the candidate's browser (via streamlit-webrtc AudioFrame),
saves to a WAV file, then transcribes with local Whisper.

No sounddevice needed — works on any server including AWS.
"""

import whisper
import tempfile
import numpy as np
import threading
import os
import wave
import queue

model = whisper.load_model("small")

_SAMPLE_RATE    = 16000
_SILENCE_RMS    = 0.003
_VAD_FRAME_MS   = 30
_VAD_RMS_THRESH = 0.004
_MIN_SPEECH_SEC = 0.8


def _trim_silence(audio: np.ndarray, fs: int) -> np.ndarray:
    frame_len = int(fs * _VAD_FRAME_MS / 1000)
    frames    = [audio[i:i+frame_len] for i in range(0, len(audio), frame_len)]
    speech_indices = [
        i for i, f in enumerate(frames)
        if len(f) > 0 and np.sqrt(np.mean(f.astype(np.float32)**2)) > _VAD_RMS_THRESH
    ]
    if not speech_indices:
        return audio
    start = max(0, speech_indices[0] - 2) * frame_len
    end   = min(len(frames), speech_indices[-1] + 3) * frame_len
    return audio[start:end]


def _has_enough_speech(audio: np.ndarray, fs: int) -> bool:
    frame_len     = int(fs * _VAD_FRAME_MS / 1000)
    frames        = [audio[i:i+frame_len] for i in range(0, len(audio), frame_len)]
    speech_frames = sum(
        1 for f in frames
        if len(f) > 0 and np.sqrt(np.mean(f.astype(np.float32)**2)) > _VAD_RMS_THRESH
    )
    return (speech_frames * _VAD_FRAME_MS / 1000) >= _MIN_SPEECH_SEC


def save_audio_frames_to_wav(frames: list, sample_rate: int = 16000) -> str:
    """
    Save a list of numpy audio chunks to a temporary WAV file.
    Returns the path to the WAV file.
    Called from app.py after browser recording is complete.
    """
    if not frames:
        return None

    try:
        audio = np.concatenate(frames).flatten()

        # Convert to int16 for WAV
        if audio.dtype != np.int16:
            if audio.max() <= 1.0:
                audio = (audio * 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        with wave.open(tmp_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())

        return tmp_path
    except Exception as e:
        print(f"[whisper_audio] save_audio_frames_to_wav error: {e}")
        return None


def transcribe_wav(wav_path: str, container: dict, duration: int = 60):
    """
    Transcribe a WAV file using local Whisper in a background thread.
    Sets container['text'], container['done'], container['wav_path'].
    """
    def task():
        try:
            if not wav_path or not os.path.exists(wav_path):
                container["text"]     = ""
                container["wav_path"] = None
                container["duration"] = duration
                container["done"]     = True
                return

            # Load and check audio
            import scipy.io.wavfile as wavfile
            fs, audio = wavfile.read(wav_path)
            audio = audio.flatten().astype(np.float32)
            if audio.max() > 1.0:
                audio = audio / 32767.0

            rms = np.sqrt(np.mean(audio ** 2))
            if rms < _SILENCE_RMS:
                container["text"]     = ""
                container["wav_path"] = None
                container["duration"] = duration
                container["done"]     = True
                return

            trimmed = _trim_silence(audio, _SAMPLE_RATE)
            if not _has_enough_speech(trimmed, _SAMPLE_RATE):
                container["text"]     = ""
                container["wav_path"] = None
                container["duration"] = duration
                container["done"]     = True
                return

            container["wav_path"] = wav_path
            container["duration"] = duration

            result = model.transcribe(
                wav_path,
                language="en",
                fp16=False,
                no_speech_threshold=0.3,
                condition_on_previous_text=False,
                temperature=0.0,
            )

            container["text"] = result["text"].strip()
            container["done"] = True

        except Exception as e:
            print(f"[whisper_audio] transcribe_wav error: {e}")
            container["text"]     = f"[Transcription error: {e}]"
            container["wav_path"] = None
            container["duration"] = duration
            container["done"]     = True

    threading.Thread(target=task, daemon=True).start()


def record_answer_background(container: dict, duration: int = 60):
    """
    Legacy compatibility shim.
    On AWS this should NOT be called — audio comes from browser.
    If somehow called, sets done=True with empty text immediately
    so the app doesn't hang waiting for a microphone that doesn't exist.
    """
    import platform
    if platform.system() != "Windows":
        # On Linux/AWS — no sounddevice, fail gracefully
        container["text"]     = ""
        container["wav_path"] = None
        container["duration"] = duration
        container["done"]     = True
        return

    # On Windows (local dev only) — try sounddevice as fallback
    try:
        import sounddevice as sd
        import scipy.io.wavfile as wavfile

        def task():
            tmp_path = None
            try:
                audio = sd.rec(
                    int(duration * _SAMPLE_RATE),
                    samplerate=_SAMPLE_RATE,
                    channels=1,
                    dtype=np.float32
                )
                sd.wait()
                audio = audio.flatten()

                rms = np.sqrt(np.mean(audio ** 2))
                if rms < _SILENCE_RMS:
                    container["text"] = ""
                    container["wav_path"] = None
                    container["duration"] = duration
                    container["done"] = True
                    return

                trimmed = _trim_silence(audio, _SAMPLE_RATE)
                if not _has_enough_speech(trimmed, _SAMPLE_RATE):
                    container["text"] = ""
                    container["wav_path"] = None
                    container["duration"] = duration
                    container["done"] = True
                    return

                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_path = tmp.name
                wavfile.write(tmp_path, _SAMPLE_RATE, trimmed)
                tmp.close()

                container["wav_path"] = tmp_path
                container["duration"] = duration

                result = model.transcribe(
                    tmp_path,
                    language="en",
                    fp16=False,
                    no_speech_threshold=0.3,
                    condition_on_previous_text=False,
                    temperature=0.0,
                )
                container["text"] = result["text"].strip()
                container["done"] = True

            except Exception as e:
                container["text"]     = f"[Transcription error: {e}]"
                container["wav_path"] = None
                container["duration"] = duration
                container["done"]     = True
                if tmp_path and os.path.exists(tmp_path):
                    try: os.unlink(tmp_path)
                    except: pass

        threading.Thread(target=task, daemon=True).start()

    except ImportError:
        container["text"]     = ""
        container["wav_path"] = None
        container["duration"] = duration
        container["done"]     = True