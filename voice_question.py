from gtts import gTTS
import os
import uuid
import time
import threading

def speak_question(text):
    def _speak():
        try:
            filename = f"temp_{uuid.uuid4()}.mp3"
            tts = gTTS(text=text, lang="en")
            tts.save(filename)
            os.startfile(filename)
            time.sleep(len(text) * 0.075 + 2)
            try:
                os.unlink(filename)
            except Exception:
                pass
        except Exception as e:
            print(f"TTS error: {e}")

    thread = threading.Thread(target=_speak, daemon=True)
    thread.start()
    thread.join(timeout=15)