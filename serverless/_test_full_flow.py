"""Full workflow test: Create Job → Add Candidate → Prepare Interview → Get Interview → Submit → Score → Get Result."""
import json
import requests
import sys

BASE = "http://localhost:3001"
HEADERS = {
    "Authorization": "Bearer local-dev-token",
    "Content-Type": "application/json",
}

def step(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

def check(resp, expected_status=200):
    ok = resp.status_code == expected_status
    icon = "✓" if ok else "✗"
    print(f"  {icon} Status: {resp.status_code} (expected {expected_status})")
    try:
        data = resp.json()
        print(f"  Response: {json.dumps(data, indent=2)[:800]}")
        return data
    except Exception:
        print(f"  Body: {resp.text[:500]}")
        return {}

# ── Step 1: Health Check ──
step("1. Health Check")
r = requests.get(f"{BASE}/health")
check(r)

# ── Step 2: List Jobs ──
step("2. List Jobs (GET /jobs)")
r = requests.get(f"{BASE}/jobs", headers=HEADERS)
data = check(r)
job_count = len(data.get("jobs", []))
print(f"  Total jobs: {job_count}")

# ── Step 3: Create Job ──
step("3. Create Job (POST /jobs)")
r = requests.post(f"{BASE}/jobs", headers=HEADERS, json={
    "title": "Full-Stack Developer Test",
    "jdText": "We need a full-stack developer with React, Node.js, and PostgreSQL experience. Must know REST APIs and CI/CD pipelines.",
    "minPassScore": 55,
})
data = check(r, 201)
job_id = data.get("job", {}).get("jobId", "")
print(f"  Created Job ID: {job_id}")
if not job_id:
    print("  FATAL: No job ID returned")
    sys.exit(1)

# ── Step 4: Verify job in list ──
step("4. Verify job appears in list")
r = requests.get(f"{BASE}/jobs", headers=HEADERS)
data = check(r)
found = any(j.get("jobId") == job_id for j in data.get("jobs", []))
print(f"  Job found in list: {found}")

# ── Step 5: Create Candidate ──
step("5. Create Candidate (POST /jobs/{jobId}/candidates)")
r = requests.post(f"{BASE}/jobs/{job_id}/candidates", headers=HEADERS, json={
    "name": "John Doe",
    "email": "john.doe@example.com",
    "resumeFilename": "john_doe_resume.pdf",
    "resumeContentType": "application/pdf",
})
data = check(r, 201)
candidate = data.get("candidate", {})
candidate_id = candidate.get("candidateId", "")
resume_upload = data.get("resumeUpload", {})
print(f"  Candidate ID: {candidate_id}")
print(f"  Resume Upload URL: {resume_upload.get('url', 'N/A')[:80]}...")
if not candidate_id:
    print("  FATAL: No candidate ID returned")
    sys.exit(1)

# ── Step 5b: Upload dummy resume PDF ──
step("5b. Upload dummy resume PDF")
upload_url = resume_upload.get("url", "")
if upload_url:
    # Build a real PDF with extractable text (PyPDF2 needs a content stream)
    resume_text = (
        "John Doe - Software Engineer. "
        "Experience: 5 years in React, Node.js, PostgreSQL, REST APIs, and CI/CD. "
        "Built production systems handling 10000 requests per second. "
        "Education: BS Computer Science, MIT. Skills: Python, TypeScript, AWS Lambda, Docker."
    )
    content_stream = f"BT /F1 12 Tf 50 700 Td ({resume_text}) Tj ET"
    stream_bytes = content_stream.encode("latin-1")
    # PDF objects
    obj1 = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    obj4 = "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    obj5 = f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1") + stream_bytes + b"\nendstream\nendobj\n"
    header = b"%PDF-1.4\n"
    parts = [obj1.encode(), obj2.encode(), obj3.encode(), obj4.encode(), obj5]
    pdf = bytearray(header)
    offsets = [0]
    for p in parts:
        offsets.append(len(pdf))
        pdf.extend(p)
    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(parts)+1}\n0000000000 65535 f \n".encode())
    for o in offsets[1:]:
        pdf.extend(f"{o:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(parts)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode())
    dummy_pdf = bytes(pdf)
    r = requests.put(upload_url, data=dummy_pdf, headers={"Content-Type": "application/pdf"})
    print(f"  {'✓' if r.status_code < 300 else '✗'} Upload status: {r.status_code}")
else:
    print("  ⚠ No upload URL returned")

# ── Step 6: List Candidates ──
step("6. List Candidates (GET /jobs/{jobId}/candidates)")
r = requests.get(f"{BASE}/jobs/{job_id}/candidates", headers=HEADERS)
data = check(r)
cand_count = len(data.get("candidates", []))
print(f"  Candidates for this job: {cand_count}")

# ── Step 7: Send Invite ──
step("7. Send Invite (PUT /jobs/{jobId}/candidates/{candidateId}/invite)")
r = requests.put(f"{BASE}/jobs/{job_id}/candidates/{candidate_id}/invite", headers=HEADERS, json={})
data = check(r)
print(f"  Interview URL: {data.get('interviewUrl', 'N/A')}")

# ── Step 8: Prepare Interview (generates questions) ──
step("8. Prepare Interview (POST .../prepare-interview)")
r = requests.post(f"{BASE}/jobs/{job_id}/candidates/{candidate_id}/prepare-interview", headers=HEADERS, json={})
data = check(r)
print(f"  Interview prepared: {bool(data)}")

# ── Step 9: Get Interview Questions ──
step("9. Get Interview (GET .../interview)")
r = requests.get(f"{BASE}/jobs/{job_id}/candidates/{candidate_id}/interview", headers=HEADERS)
data = check(r)
interview = data.get("interview", {})
questions = interview.get("questions", [])
print(f"  Candidate Name: {interview.get('candidateName', 'N/A')}")
print(f"  Questions: {len(questions)}")
for q in questions[:3]:
    print(f"    Q{q.get('questionIndex', '?')}: {q.get('question', '')[:80]}...")

# ── Step 10: Submit Interview Answers ──
step("10. Submit Interview (POST .../interview)")
answers = []
for q in questions:
    answers.append({
        "questionIndex": q.get("questionIndex", 0),
        "answerText": f"For this question about {q.get('question', '')[:30]}, I would say that in my previous role at Acme Corp, I led a team of 5 engineers to build a microservices platform using Python and React. We reduced deployment time by 60% and improved system reliability to 99.9% uptime.",
        "durationSeconds": 120,
    })
r = requests.post(f"{BASE}/jobs/{job_id}/candidates/{candidate_id}/interview", headers=HEADERS, json={
    "consentAccepted": True,
    "answers": answers,
    "integritySignals": {
        "tabSwitches": 0,
        "fullscreenExits": 0,
        "copyPasteAttempts": 0,
        "devtoolsAttempts": 0,
    },
})
data = check(r)

# ── Step 11: Trigger Scoring ──
step("11. Start Scoring (POST .../score)")
r = requests.post(f"{BASE}/jobs/{job_id}/candidates/{candidate_id}/score", headers=HEADERS, json={})
data = check(r)
print(f"  Scoring message: {data.get('message', 'N/A')}")

# ── Step 12: Get Result ──
step("12. Get Result (GET .../result)")
r = requests.get(f"{BASE}/jobs/{job_id}/candidates/{candidate_id}/result", headers=HEADERS)
data = check(r)
result = data.get("result", {})
if result:
    print(f"  Final Score: {result.get('finalScore', 'N/A')}")
    print(f"  Recommendation: {result.get('recommendation', 'N/A')}")
    print(f"  Summary: {result.get('summary', 'N/A')[:200]}")
    per_q = result.get("perQuestion", [])
    for pq in per_q[:3]:
        print(f"    Q{pq.get('questionIndex')}: score={pq.get('score')} verdict={pq.get('verdict')}")

# ── Step 13: Job Stats ──
step("13. Job Stats (GET /jobs/{jobId}/stats)")
r = requests.get(f"{BASE}/jobs/{job_id}/stats", headers=HEADERS)
data = check(r)

print("\n" + "="*60)
print("  FULL WORKFLOW TEST COMPLETE")
print("="*60)
print(f"  Job ID:       {job_id}")
print(f"  Candidate ID: {candidate_id}")
print(f"  All steps executed.")
print()
