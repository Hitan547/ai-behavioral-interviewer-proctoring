"""Create a job + candidate + prepare interview so candidate URL works."""
import requests
import json

BASE = "http://localhost:3001"
H = {
    "Authorization": "Bearer local-dev-token",
    "Content-Type": "application/json",
    "x-org-id": "local-org",
    "x-user-id": "local-user-001",
    "x-user-email": "recruiter@psysense.local",
}

# 1. Create job
r = requests.post(f"{BASE}/jobs", headers=H, json={
    "title": "Frontend React Developer",
    "jdText": "Looking for React developer with 3+ years TypeScript, Next.js, REST APIs, testing.",
    "minPassScore": 60,
})
job = r.json()["job"]
job_id = job["jobId"]
print(f"[1] Job created: {job_id}")

# 2. Create candidate
r = requests.post(f"{BASE}/jobs/{job_id}/candidates", headers=H, json={
    "name": "Hitan K",
    "email": "hitan@example.com",
    "resumeFilename": "Hitan_K_resume.pdf",
    "resumeContentType": "application/pdf",
})
cand = r.json()
cand_id = cand["candidate"]["candidateId"]
upload_url = cand["resumeUpload"]["url"]
print(f"[2] Candidate created: {cand_id}")

# 3. Upload dummy resume PDF with text
resume_text = (
    "Hitan K - Cybersecurity and Software Engineer. "
    "Experience: Python, React, AWS Lambda, Docker, PostgreSQL. "
    "Built AI interview platform with proctoring and LLM scoring."
)
content_stream = f"BT /F1 12 Tf 50 700 Td ({resume_text}) Tj ET"
stream_bytes = content_stream.encode("latin-1")
obj1 = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
obj2 = "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
obj3 = "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
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
r = requests.put(upload_url, data=bytes(pdf), headers={"Content-Type": "application/pdf"})
print(f"[3] Resume uploaded: {r.status_code}")

# 4. Prepare interview (generates questions)
r = requests.post(f"{BASE}/jobs/{job_id}/candidates/{cand_id}/prepare-interview", headers=H, json={})
status = r.json().get("interview", {}).get("interviewStatus", "?")
print(f"[4] Prepare interview: {r.status_code} - {status}")

# 5. Send invite
r = requests.put(f"{BASE}/jobs/{job_id}/candidates/{cand_id}/invite", headers=H, json={})
print(f"[5] Invite sent: {r.status_code}")

# 6. Print candidate URL
print()
print("=" * 60)
print("  CANDIDATE INTERVIEW URL (open in browser):")
print("=" * 60)
print(f"  http://localhost:5174/?mode=candidate&jobId={job_id}&candidateId={cand_id}")
print("=" * 60)
