"""
debug_check.py
--------------
Run this ONCE from your project root to diagnose why questions fall back to defaults.

    python debug_check.py

Checks:
1. .env file found and GROQ_API_KEY loaded
2. Groq API reachable and key valid
3. LLM returns valid JSON for a test question generation
4. PDF extraction works (if you pass a resume path)
"""

import os, sys, json, re

print("=" * 60)
print("PsySense Diagnostic")
print("=" * 60)

# ── 1. .env ────────────────────────────────────────────────────────
print("\n[1] Checking .env file...")
env_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(env_path):
    print(f"  ✅ Found: {env_path}")
else:
    print(f"  ❌ NOT FOUND at {env_path}")
    print("  Create a .env file in your project root with:")
    print("      GROQ_API_KEY=gsk_your_key_here")

from dotenv import load_dotenv
loaded = load_dotenv(dotenv_path=env_path, override=True)
print(f"  load_dotenv result: {loaded}")

# ── 2. API key ─────────────────────────────────────────────────────
print("\n[2] Checking GROQ_API_KEY...")
key = os.environ.get("GROQ_API_KEY", "")
if key and key.startswith("gsk_"):
    print(f"  ✅ Key loaded: {key[:12]}...{key[-4:]}")
elif key:
    print(f"  ⚠️  Key found but unusual format: {key[:8]}...")
else:
    print("  ❌ GROQ_API_KEY is empty or not set")
    print("  Fix: add GROQ_API_KEY=gsk_... to your .env file")
    sys.exit(1)

# ── 3. Groq API call ───────────────────────────────────────────────
print("\n[3] Testing Groq API call...")
try:
    from groq import Groq
    client = Groq(api_key=key)
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": 'Return exactly this JSON and nothing else: ["test question?"]'}],
        temperature=0.1,
        max_tokens=50,
    )
    raw = response.choices[0].message.content.strip()
    print(f"  Raw response: {raw!r}")
    raw = re.sub(r"```json|```", "", raw).strip()
    parsed = json.loads(raw)
    print(f"  ✅ Groq working. Parsed: {parsed}")
except Exception as e:
    print(f"  ❌ Groq call failed: {e}")
    sys.exit(1)

# ── 4. Full question generation test ──────────────────────────────
print("\n[4] Testing question generation with dummy resume...")
dummy_resume = """
John Doe — Software Engineer
Skills: Python, FastAPI, React, PostgreSQL, Docker
Projects:
- Built REST API for e-commerce platform using FastAPI and PostgreSQL
- Deployed ML pipeline on AWS using Docker and Lambda
Education: B.Tech Computer Science, 2023
Internship: Backend Developer at XYZ Corp, built microservices architecture
"""

try:
    sys.path.insert(0, os.getcwd())
    from resume_parser import generate_questions
    questions = generate_questions(dummy_resume)
    print(f"  Got {len(questions)} questions:")
    for i, q in enumerate(questions):
        print(f"    Q{i+1}: {q[:80]}...")
    
    # Check if they're fallback
    fallback_q1 = "Walk me through a project you built end-to-end"
    if fallback_q1 in questions[0]:
        print("\n  ⚠️  FALLBACK QUESTIONS RETURNED — LLM call failed silently")
        print("  This means the Groq call in resume_parser.py is failing.")
        print("  Check the [resume_parser] lines printed above.")
    else:
        print("\n  ✅ Custom questions generated — LLM is working correctly!")
except Exception as e:
    print(f"  ❌ generate_questions() threw: {e}")
    import traceback; traceback.print_exc()

# ── 5. PDF extraction (optional) ──────────────────────────────────
print("\n[5] PDF extraction...")
if len(sys.argv) > 1:
    pdf_path = sys.argv[1]
    try:
        from resume_parser import extract_resume_text
        text = extract_resume_text(pdf_path)
        print(f"  ✅ Extracted {len(text)} characters from {pdf_path}")
        print(f"  First 200 chars: {text[:200]!r}")
        if len(text) < 100:
            print("  ⚠️  Very short extraction — PDF may be image-based (not text-searchable)")
    except Exception as e:
        print(f"  ❌ PDF extraction failed: {e}")
else:
    print("  (skipped — pass a PDF path as argument: python debug_check.py resume.pdf)")

print("\n" + "=" * 60)
print("Diagnostic complete.")
print("=" * 60)