import json
import os
import sys
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from handlers import candidates
from repositories.candidates_repository import CandidatesRepository


class FakeDynamoTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        key = (Item["pk"], Item["sk"])
        if key in self.items:
            raise AssertionError("duplicate key")
        self.items[key] = dict(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def query(self, KeyConditionExpression=None, ExpressionAttributeValues=None, ScanIndexForward=True):
        pk = ExpressionAttributeValues[":pk"]
        prefix = ExpressionAttributeValues[":prefix"]
        found = [
            item for (item_pk, item_sk), item in self.items.items()
            if item_pk == pk and item_sk.startswith(prefix)
        ]
        found.sort(key=lambda item: item["sk"], reverse=not ScanIndexForward)
        return {"Items": found}


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn, HttpMethod):
        self.calls.append({
            "ClientMethod": ClientMethod,
            "Params": Params,
            "ExpiresIn": ExpiresIn,
            "HttpMethod": HttpMethod,
        })
        return f"https://upload.example.test/{Params['Key']}"


def _event(method, job_id="job-123", body=None, org_id="org-123", user_id="user-123"):
    return {
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:org_id": org_id,
                        "sub": user_id,
                        "email": "recruiter@example.com",
                        "custom:role": "recruiter",
                    }
                }
            },
        },
        "pathParameters": {"jobId": job_id},
        "body": json.dumps(body or {}),
    }


def _repo(table=None, s3=None):
    return CandidatesRepository(
        table or FakeDynamoTable(),
        s3 or FakeS3Client(),
        "psysense-dev-artifacts",
    )


def test_create_candidate_writes_metadata_and_presigns_resume_upload(monkeypatch):
    table = FakeDynamoTable()
    s3 = FakeS3Client()
    monkeypatch.setattr(candidates, "_get_repository", lambda: _repo(table, s3))

    response = candidates.handler(_event("POST", body={
        "name": "Asha Kumar",
        "email": "ASHA@example.com",
        "resumeFilename": "Asha Resume.pdf",
        "resumeContentType": "application/pdf",
        "collegeName": "ABC Engineering College",
        "department": "CSE",
        "graduationYear": "2026",
    }), None)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])
    candidate = payload["candidate"]
    upload = payload["resumeUpload"]
    assert candidate["orgId"] == "org-123"
    assert candidate["jobId"] == "job-123"
    assert candidate["email"] == "asha@example.com"
    assert candidate["collegeName"] == "ABC Engineering College"
    assert candidate["department"] == "CSE"
    assert candidate["graduationYear"] == "2026"
    assert candidate["interviewStatus"] == "Resume Upload Pending"
    assert upload["method"] == "PUT"
    assert upload["headers"]["Content-Type"] == "application/pdf"
    assert upload["key"].startswith(f"resumes/org-123/job-123/{candidate['candidateId']}/")
    assert upload["key"].endswith("Asha-Resume.pdf")
    assert s3.calls[0]["Params"]["Bucket"] == "psysense-dev-artifacts"
    stored = next(iter(table.items.values()))
    assert stored["pk"] == "ORG#org-123#JOB#job-123"
    assert stored["sk"].startswith("CANDIDATE#")
    assert stored["collegeName"] == "ABC Engineering College"


def test_list_candidates_returns_only_current_job(monkeypatch):
    table = FakeDynamoTable()
    repo = _repo(table)
    repo.create_candidate(
        org_id="org-123",
        job_id="job-123",
        recruiter_id="user-123",
        name="Visible Candidate",
        email="visible@example.com",
        resume_filename="visible.pdf",
        resume_content_type="application/pdf",
    )
    repo.create_candidate(
        org_id="org-123",
        job_id="job-999",
        recruiter_id="user-123",
        name="Other Job Candidate",
        email="hidden@example.com",
        resume_filename="hidden.pdf",
        resume_content_type="application/pdf",
    )
    monkeypatch.setattr(candidates, "_get_repository", lambda: repo)

    response = candidates.handler(_event("GET", job_id="job-123"), None)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert [candidate["name"] for candidate in payload["candidates"]] == ["Visible Candidate"]


def test_create_candidate_requires_valid_pdf_resume(monkeypatch):
    monkeypatch.setattr(candidates, "_get_repository", lambda: _repo())

    response = candidates.handler(_event("POST", body={
        "name": "Asha Kumar",
        "email": "asha@example.com",
        "resumeFilename": "resume.docx",
    }), None)

    assert response["statusCode"] == 400
    assert "PDF" in json.loads(response["body"])["error"]


def test_create_candidate_requires_job_path(monkeypatch):
    monkeypatch.setattr(candidates, "_get_repository", lambda: _repo())

    response = candidates.handler(_event("POST", job_id="", body={
        "name": "Asha Kumar",
        "email": "asha@example.com",
        "resumeFilename": "resume.pdf",
    }), None)

    assert response["statusCode"] == 400
    assert "jobId" in json.loads(response["body"])["error"]
