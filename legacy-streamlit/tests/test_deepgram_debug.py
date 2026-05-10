"""Debug Deepgram API response."""
import sys, os, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
dg_key = os.getenv("DEEPGRAM_API_KEY")

wav = os.path.join(os.path.dirname(__file__), "debug_audio", "last_recording.wav")

with open(wav, "rb") as f:
    audio_data = f.read()

print(f"Key: {dg_key[:10]}...")
print(f"Audio size: {len(audio_data):,} bytes")

resp = requests.post(
    "https://api.deepgram.com/v1/listen?model=nova-2&language=en",
    headers={"Authorization": f"Token {dg_key}", "Content-Type": "audio/wav"},
    data=audio_data,
    timeout=60,
)
print(f"Status: {resp.status_code}")
body = resp.text[:1000]
print(f"Body: {body}")
