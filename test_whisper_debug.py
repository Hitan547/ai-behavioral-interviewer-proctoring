"""Test LLM post-correction of garbled Whisper transcript."""
import os, sys, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

groq_key = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY")
wav_path = os.path.join(os.path.dirname(__file__), "debug_audio", "last_recording.wav")

# Step 1: Get Whisper transcript (garbled)
vocab = (
    "PsySense, WebRTC, Whisper, librosa, prosody, multimodal, pipeline, "
    "transcription, pitch, energy, speech rate, fluency, confidence, "
    "chunk-based, timestamps, buffering, preprocessing, filtering, "
    "latency, synchronization, behavioral, scoring, ASR. "
)
with open(wav_path, "rb") as f:
    resp = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {groq_key}"},
        files={"file": ("audio.wav", f, "audio/wav")},
        data={"model": "whisper-large-v3", "language": "en",
              "response_format": "text", "prompt": vocab, "temperature": "0"},
        timeout=60,
    )
raw_transcript = resp.text.strip() if resp.ok else ""
print("=== RAW WHISPER TRANSCRIPT ===")
print(raw_transcript[:600])

# Step 2: LLM post-correction
question = (
    "How did you approach the integration of Whisper ASR, WebRTC, "
    "and librosa prosody in the PsySense platform, and what were "
    "some of the challenges you faced?"
)
correction_prompt = f"""You are a transcript correction assistant. A speech-to-text system produced a garbled transcript from a technical interview answer. The audio quality was poor, causing many words to be misheard.

Your task: Reconstruct what the candidate ACTUALLY SAID by fixing misheard words. Use the interview question and the candidate's resume context to identify the correct technical terms.

Rules:
1. Fix obvious misheard words (e.g., "vulnerability" was likely "modularity", "influence" was likely "inference")
2. Keep the candidate's actual sentence structure and speaking style
3. Do NOT add information the candidate didn't say
4. Do NOT paraphrase — fix individual words, keep the flow
5. If a section is too garbled to reconstruct, mark it as [unclear]
6. Preserve fillers like "um", "uh", "so", "like" — they are real

Interview Question: {question}

Technical vocabulary the candidate likely used: WebRTC, Whisper, librosa, prosody, multimodal, pipeline, transcription, pitch, energy, speech rate, fluency, confidence, chunk-based processing, timestamps, buffering, preprocessing, filtering, latency, synchronization, behavioral insights, scoring, ASR, PsySense

Garbled transcript:
{raw_transcript}

Corrected transcript:"""

resp2 = requests.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": correction_prompt}],
        "temperature": 0,
        "max_tokens": 1000,
    },
    timeout=60,
)
if resp2.ok:
    corrected = resp2.json()["choices"][0]["message"]["content"]
    print("\n=== LLM-CORRECTED TRANSCRIPT ===")
    print(corrected[:800])
else:
    print(f"\nERROR: {resp2.status_code}: {resp2.text[:300]}")
