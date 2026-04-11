"""
voice_question.py
-----------------
Speaks the interview question to the candidate.

Local (Windows): gTTS generates MP3, plays via os.startfile
AWS / Linux:     question text is displayed visually only —
                 browser TTS is handled client-side via st.markdown
                 No server-side audio playback on Linux.
"""

import os
import uuid
import time
import threading
import platform


def speak_question(text: str):
    """
    Attempt to play question audio.
    On Linux/AWS: silently skips — question is shown as text on screen.
    On Windows:   plays via gTTS + os.startfile (local dev only).
    """
    if platform.system() != "Windows":
        # On AWS/Linux — no os.startfile, no speaker output
        # Candidate reads the question from the card on screen
        return

    def _speak():
        try:
            from gtts import gTTS
            filename = f"temp_{uuid.uuid4()}.mp3"
            tts = gTTS(text=text, lang="en", slow=False)
            tts.save(filename)
            time.sleep(0.3)
            os.startfile(filename)
            time.sleep(max(len(text) * 0.08, 4))
            try:
                os.unlink(filename)
            except Exception:
                pass
        except Exception as e:
            print(f"[voice_question] TTS error: {e}")

    thread = threading.Thread(target=_speak, daemon=True)
    thread.start()
    thread.join(timeout=20)