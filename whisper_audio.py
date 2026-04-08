"""
whisper_audio.py
----------------
Background audio recorder + local Whisper transcriber.

Changes vs previous version:
- wav_path stored in container dict so voice_scorer.py can read it
- WAV file NOT deleted immediately — voice scorer reads it first
- demo_app.py deletes WAV after voice scoring is complete
"""
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
import tempfile
import numpy as np
import threading
import os

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
        if np.sqrt(np.mean(f**2)) > _VAD_RMS_THRESH
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
        if np.sqrt(np.mean(f**2)) > _VAD_RMS_THRESH
    )
    return (speech_frames * _VAD_FRAME_MS / 1000) >= _MIN_SPEECH_SEC


def record_answer_background(container: dict, duration: int = 60):
    """
    Record audio in background thread and transcribe with Whisper.

    Container keys set:
        text     : str   transcript
        done     : bool  True when complete
        wav_path : str   path to WAV file for voice scoring (None on failure)
        duration : int   recording duration in seconds
    """
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

            # Write WAV — keep for voice scorer
            tmp      = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            wav.write(tmp_path, _SAMPLE_RATE, trimmed)
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

            # WAV is NOT deleted here — demo_app.py deletes after voice scoring

        except Exception as e:
            container["text"]     = f"[Transcription error: {e}]"
            container["wav_path"] = None
            container["duration"] = duration
            container["done"]     = True
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    threading.Thread(target=task, daemon=True).start()