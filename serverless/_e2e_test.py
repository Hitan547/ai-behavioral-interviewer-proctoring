"""End-to-end API test of the full PsySense flow."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import os
import urllib.request
import urllib.error

BASE = "http://localhost:3001"
PASS_COUNT = 0
FAIL_COUNT = 0

def api(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            return e.code, json.loads(body_text)
        except:
            return e.code, {"raw": body_text[:300]}

def test(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {name} -- {detail}")

print("\n" + "="*60)
print("  PsySense End-to-End API Test")
print("="*60)

# -- Step 1: Health Check --
print("\n-- Step 1: Health Check --")
status, data = api("GET", "/health")
test("Health endpoint returns 200", status == 200)
test("Status is ok", data.get("status") == "ok")

# -- Step 2: Recruiter Signup --
print("\n-- Step 2: Recruiter Signup --")
status, data = api("POST", "/auth/recruiter-signup", {
    "email": "e2e-v2@psysense.ai",
    "password": "TestPass123",
    "orgName": "E2E Test Corp V2"
})
if status == 409:
    # Already exists, login instead
    status, data = api("POST", "/auth/recruiter-login", {
        "email": "e2e-v2@psysense.ai",
        "password": "TestPass123",
    })
    test("Recruiter login (already exists)", status == 200, f"got {status}")
else:
    test("Signup returns 201", status == 201, f"got {status}: {data}")
recruiter_token = data.get("accessToken", "")
org_id = data.get("orgId", "")
test("Got access token", bool(recruiter_token))
test("Got org ID", bool(org_id))

# -- Step 3: Recruiter Login --
print("\n-- Step 3: Recruiter Login --")
status, data = api("POST", "/auth/recruiter-login", {
    "email": "e2e-v2@psysense.ai",
    "password": "TestPass123",
})
test("Login returns 200", status == 200, f"got {status}: {data}")
recruiter_token = data.get("accessToken", recruiter_token)
test("Login returns token", bool(data.get("accessToken")))

# -- Step 4: Create Job --
print("\n-- Step 4: Create Job --")
status, data = api("POST", "/jobs", {
    "title": "E2E Test - Senior Engineer",
    "jdText": "We need a senior Python developer with AWS experience. Must know DynamoDB, Lambda, and API Gateway. Experience with React and TypeScript is a plus.",
    "minPassScore": 60,
    "shortlistThreshold": 7,
}, token=recruiter_token)
test("Create job returns 201", status == 201, f"got {status}: {data}")
job = data.get("job", {})
job_id = job.get("jobId", "")
test("Job has ID", bool(job_id))

# -- Step 5: List Jobs --
print("\n-- Step 5: List Jobs --")
status, data = api("GET", "/jobs", token=recruiter_token)
test("List jobs returns 200", status == 200)
test("At least 1 job returned", len(data.get("jobs", [])) >= 1)

# -- Step 6: Get Job Stats --
print("\n-- Step 6: Get Job Stats --")
status, data = api("GET", f"/jobs/{job_id}/stats", token=recruiter_token)
test("Stats returns 200", status == 200, f"got {status}")
test("Stats has total field", "total" in data.get("stats", {}))

# -- Step 7: Create Candidate --
print("\n-- Step 7: Create Candidate --")
status, data = api("POST", f"/jobs/{job_id}/candidates", {
    "name": "E2E Test Candidate",
    "email": "candidate-v2@e2e-test.com",
    "resumeFilename": "resume.pdf",
}, token=recruiter_token)
test("Create candidate returns 201", status == 201, f"got {status}: {data}")
candidate = data.get("candidate", {})
candidate_id = candidate.get("candidateId", "")
resume_upload = data.get("resumeUpload", {})
test("Candidate has ID", bool(candidate_id))
test("Got resume upload URL", bool(resume_upload.get("url")))

# -- Step 7b: Upload a fake resume PDF --
print("\n-- Step 7b: Upload Resume PDF --")
# Create a minimal valid PDF with some text
pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 280>>stream
BT
/F1 12 Tf
72 720 Td
(John Doe - Senior Software Engineer) Tj
0 -20 Td
(Experience: 8 years Python, AWS Lambda, DynamoDB) Tj
0 -20 Td
(Skills: Python, JavaScript, React, TypeScript, AWS) Tj
0 -20 Td
(Education: BS Computer Science, MIT 2016) Tj
0 -20 Td
(Previous: Senior Dev at Google, Tech Lead at Meta) Tj
ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000598 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
665
%%EOF"""
upload_url = resume_upload.get("url", "")
if upload_url:
    try:
        req = urllib.request.Request(upload_url, data=pdf_content, method="PUT",
            headers={"Content-Type": "application/pdf"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            test("Resume upload succeeded", resp.status in (200, 204))
    except Exception as e:
        test("Resume upload succeeded", False, str(e))
else:
    test("Resume upload URL available", False, "no URL")

# -- Step 8: List Candidates --
print("\n-- Step 8: List Candidates --")
status, data = api("GET", f"/jobs/{job_id}/candidates", token=recruiter_token)
test("List candidates returns 200", status == 200)
test("At least 1 candidate", len(data.get("candidates", [])) >= 1)

# -- Step 9: Update Candidate (shortlist) --
print("\n-- Step 9: Update Candidate (shortlist) --")
status, data = api("PUT", f"/jobs/{job_id}/candidates/{candidate_id}", {
    "shortlisted": True,
}, token=recruiter_token)
test("Update candidate returns 200", status == 200, f"got {status}: {json.dumps(data)[:200]}")
if status == 200:
    test("Candidate is shortlisted", data.get("candidate", {}).get("shortlisted") == True)

# -- Step 10: Prepare Interview (generates questions via Groq) --
print("\n-- Step 10: Prepare Interview (Groq API call) --")
status, data = api("POST", f"/jobs/{job_id}/candidates/{candidate_id}/prepare-interview", {}, token=recruiter_token)
test("Prepare interview returns 200", status == 200, f"got {status}: {json.dumps(data)[:300]}")
interview = data.get("interview", {})
questions = interview.get("questions", [])
test("Got questions", len(questions) >= 1, f"got {len(questions)} questions")
if questions:
    q1 = questions[0] if isinstance(questions[0], str) else questions[0].get("question", "")
    test("First question has text", bool(q1), f"q1={q1!r}")
    print(f"       Q1: {q1[:80]}...")

# -- Step 11: Candidate Login --
print("\n-- Step 11: Candidate Login --")
import boto3
ddb = boto3.resource("dynamodb", endpoint_url="http://localhost:8000", region_name="us-east-1",
                      aws_access_key_id="local", aws_secret_access_key="local")
table = ddb.Table("psysense-local")
table.update_item(
    Key={"pk": f"ORG#{org_id}#JOB#{job_id}", "sk": f"CANDIDATE#{candidate_id}"},
    UpdateExpression="SET invitePassword = :pw, interviewStatus = :status",
    ExpressionAttributeValues={":pw": "TEST-PW", ":status": "Invited"},
)
status, data = api("POST", "/auth/candidate-login", {
    "username": "candidate-v2@e2e-test.com",
    "password": "TEST-PW",
    "orgId": org_id,
    "jobId": job_id,
    "candidateId": candidate_id,
})
test("Candidate login returns 200", status == 200, f"got {status}: {data}")
candidate_token = data.get("accessToken", "")
test("Got candidate token", bool(candidate_token))

# -- Step 12: Get Interview (as candidate) --
print("\n-- Step 12: Get Interview (as candidate) --")
status, data = api("GET", f"/jobs/{job_id}/candidates/{candidate_id}/interview", token=candidate_token)
test("Get interview returns 200", status == 200, f"got {status}: {json.dumps(data)[:200]}")
interview = data.get("interview", {})
test("Interview has questions", len(interview.get("questions", [])) >= 1)
test("Has candidate name", bool(interview.get("candidateName")))

# -- Step 13: Submit Interview --
print("\n-- Step 13: Submit Interview --")
answers = []
for i, q in enumerate(interview.get("questions", [])[:5]):
    answers.append({
        "questionIndex": q["questionIndex"],
        "answerText": f"In my 8 years of experience as a senior Python developer, I have built several microservices using AWS Lambda and DynamoDB. For question {i+1}, I would approach this by leveraging my expertise in distributed systems and cloud architecture.",
        "durationSeconds": 45 + i * 10,
    })
if not answers:
    test("Have answers to submit", False, "no questions available")
else:
    status, data = api("POST", f"/jobs/{job_id}/candidates/{candidate_id}/interview", {
        "consentAccepted": True,
        "answers": answers,
        "integritySignals": {
            "tabSwitches": 1,
            "fullscreenExits": 0,
            "copyPasteAttempts": 0,
            "devtoolsAttempts": 0,
            "screenCount": 1,
            "faceNotDetected": 2,
            "multipleFaces": 0,
            "events": [{"type": "tab_switch", "questionIndex": 0, "timestamp": "2026-05-09T00:00:00Z"}],
        },
    }, token=candidate_token)
    test("Submit interview returns 201", status == 201, f"got {status}: {data}")
    submission = data.get("submission", {})
    test("Submission has ID", bool(submission.get("submissionId")))
    test("Status is Interview Submitted", submission.get("interviewStatus") == "Interview Submitted")
    test("Integrity signals captured", submission.get("integritySignals", {}).get("tabSwitches") == 1)
    test("Risk score computed", submission.get("integritySignals", {}).get("riskScore", -1) >= 0)

# -- Step 14: Score Interview --
print("\n-- Step 14: Score Interview (Groq LLM scoring) --")
status, data = api("POST", f"/jobs/{job_id}/candidates/{candidate_id}/score", {}, token=recruiter_token)
test("Start scoring returns 200/202", status in (200, 201, 202), f"got {status}: {data}")

# -- Step 15: Get Result --
print("\n-- Step 15: Get Scoring Result --")
import time
time.sleep(3)
status, data = api("GET", f"/jobs/{job_id}/candidates/{candidate_id}/result", token=recruiter_token)
test("Get result returns 200", status == 200, f"got {status}: {json.dumps(data)[:200]}")
result = data.get("result", {})
if result:
    test("Result has final score", "finalScore" in result, f"keys: {list(result.keys())}")
    final_score = result.get("finalScore", "N/A")
    print(f"       Final Score: {final_score}")
    if isinstance(result.get("dimensionScores"), list):
        for dim in result["dimensionScores"]:
            print(f"       {dim.get('dimension', '?')}: {dim.get('score', '?')}/10")

# -- Step 16: Close Job --
print("\n-- Step 16: Close Job --")
status, data = api("PUT", f"/jobs/{job_id}", {"status": "Closed"}, token=recruiter_token)
test("Close job returns 200", status == 200, f"got {status}")
test("Job status is Closed", data.get("job", {}).get("status") == "Closed")

# -- Summary --
print("\n" + "="*60)
total = PASS_COUNT + FAIL_COUNT
print(f"  RESULTS: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
if FAIL_COUNT == 0:
    print("  ALL TESTS PASSED!")
print("="*60 + "\n")
