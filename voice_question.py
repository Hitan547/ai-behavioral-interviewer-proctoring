from gtts import gTTS
import os
import uuid
import time
import threading

def speak_question(text):
    def _speak():
        try:
            filename = f"temp_{uuid.uuid4()}.mp3"
            tts = gTTS(text=text, lang="en", slow=False)
            tts.save(filename)
            time.sleep(0.3)  # small buffer before playing
            os.startfile(filename)
            time.sleep(max(len(text) * 0.08, 4))  # wait longer
            try:
                os.unlink(filename)
            except Exception:
                pass
        except Exception as e:
            print(f"TTS error: {e}")

    thread = threading.Thread(target=_speak, daemon=True)
    thread.start()
    thread.join(timeout=20)  # increased timeout