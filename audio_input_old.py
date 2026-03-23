import speech_recognition as sr
import threading
import time

def record_answer_background(container, duration=60, chunk=5):

    recognizer = sr.Recognizer()

    def record():

        full_text = ""

        try:
            with sr.Microphone() as source:

                recognizer.energy_threshold = 250
                recognizer.pause_threshold = 1.2
                recognizer.dynamic_energy_threshold = True

                recognizer.adjust_for_ambient_noise(source, duration=2)

                start = time.time()

                while time.time() - start < duration:

                    try:
                        audio = recognizer.listen(
                            source,
                            timeout=None,
                            phrase_time_limit=chunk
                        )

                        text = recognizer.recognize_google(audio)

                        full_text += " " + text

                    except sr.UnknownValueError:
                        pass

                    except sr.RequestError:
                        pass

        except:
            pass

        container["text"] = full_text.strip()
        container["done"] = True

    thread = threading.Thread(target=record)
    thread.start()