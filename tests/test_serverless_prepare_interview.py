import json
import os
import sys
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from handlers import prepare_interview
from repositories.interviews_repository import InterviewsRepository


class FakeBody:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class FakeDynamoTable:
    def __init__(self):
        self.items = {}
        self.updated = []

    def get_item(self, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def update_item(
        self,
        Key,
        UpdateExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        ConditionExpression=None,
    ):
        key = (Key["pk"], Key["sk"])
        if key not in self.items:
            raise AssertionError("missing candidate")
        self.updated.append({
            "Key": Key,
            "UpdateExpression": UpdateExpression,
            "ExpressionAttributeValues": ExpressionAttributeValues,
            "ConditionExpression": ConditionExpression,
        })
        self.items[key].update({
            "interviewStatus": ExpressionAttributeValues[":status"],
            "questions": ExpressionAttributeValues[":questions"],
            "questionKeywords": ExpressionAttributeValues[":keywords"],
            "vocab": ExpressionAttributeValues[":vocab"],
            "resumeTextPreview": ExpressionAttributeValues[":preview"],
            "preparedBy": ExpressionAttributeValues[":preparedBy"],
            "preparedAt": ExpressionAttributeValues[":preparedAt"],
            "updatedAt": ExpressionAttributeValues[":updatedAt"],
        })
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class FakeS3Client:
    def __init__(self, objects):
        self.objects = objects

    def get_object(self, Bucket, Key):
        return {"Body": FakeBody(self.objects[(Bucket, Key)])}


def _event(method="POST", job_id="job-123", candidate_id="cand-123", org_id="org-123", user_id="user-123"):
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
        "pathParameters": {
            "jobId": job_id,
            "candidateId": candidate_id,
        },
    }


def _repo():
    table = FakeDynamoTable()
    table.items[("ORG#org-123", "JOB#job-123")] = {
        "pk": "ORG#org-123",
        "sk": "JOB#job-123",
        "orgId": "org-123",
        "jobId": "job-123",
        "title": "Backend Engineer",
        "jdText": "Build APIs with Python and AWS.",
    }
    table.items[("ORG#org-123#JOB#job-123", "CANDIDATE#cand-123")] = {
        "pk": "ORG#org-123#JOB#job-123",
        "sk": "CANDIDATE#cand-123",
        "orgId": "org-123",
        "jobId": "job-123",
        "candidateId": "cand-123",
        "name": "Asha Kumar",
        "email": "asha@example.com",
        "resumeS3Bucket": "psysense-dev-artifacts",
        "resumeS3Key": "resumes/org-123/job-123/cand-123/resume.pdf",
    }
    s3 = FakeS3Client({
        ("psysense-dev-artifacts", "resumes/org-123/job-123/cand-123/resume.pdf"): b"fake-pdf",
    })
    return InterviewsRepository(table, s3, "psysense-dev-artifacts"), table


def test_prepare_interview_reads_resume_generates_questions_and_updates_candidate(monkeypatch):
    repo, table = _repo()
    monkeypatch.setattr(prepare_interview, "_get_repository", lambda: repo)
    monkeypatch.setattr(
        prepare_interview,
        "extract_resume_text_from_pdf_bytes",
        lambda data: "Asha built Python APIs on AWS Lambda and DynamoDB.",
    )
    monkeypatch.setattr(
        prepare_interview,
        "generate_questions_with_keywords",
        lambda resume_text, jd_text="", seed_context="": (
            [
                "How did you design the Python APIs?",
                "How did you use AWS Lambda?",
                "How did you model DynamoDB data?",
                "Tell me about a delivery challenge.",
                "Why are you a fit for this role?",
            ],
            [["Python", "API"], ["Lambda"], ["DynamoDB"], [], ["AWS"]],
            {"domain": "software_engineering", "terms": ["Python", "Lambda", "DynamoDB"]},
        ),
    )

    response = prepare_interview.handler(_event(), None)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    interview = payload["interview"]
    assert interview["interviewStatus"] == "Interview Prepared"
    assert interview["candidateId"] == "cand-123"
    assert len(interview["questions"]) == 5
    updated = table.items[("ORG#org-123#JOB#job-123", "CANDIDATE#cand-123")]
    assert updated["preparedBy"] == "user-123"
    assert updated["resumeTextPreview"].startswith("Asha built Python APIs")


def test_prepare_interview_rejects_missing_candidate(monkeypatch):
    repo, _table = _repo()
    monkeypatch.setattr(prepare_interview, "_get_repository", lambda: repo)

    response = prepare_interview.handler(_event(candidate_id="missing"), None)

    assert response["statusCode"] == 404
    assert "Candidate" in json.loads(response["body"])["error"]


def test_prepare_interview_requires_post(monkeypatch):
    repo, _table = _repo()
    monkeypatch.setattr(prepare_interview, "_get_repository", lambda: repo)

    response = prepare_interview.handler(_event(method="GET"), None)

    assert response["statusCode"] == 405
