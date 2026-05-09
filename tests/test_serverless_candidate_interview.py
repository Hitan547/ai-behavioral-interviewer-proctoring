import json
import os
import sys
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from handlers import candidate_interview
from repositories.candidate_interviews_repository import CandidateInterviewsRepository


class FakeDynamoTable:
    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def put_item(self, Item, ConditionExpression=None):
        key = (Item["pk"], Item["sk"])
        if key in self.items:
            raise AssertionError("duplicate key")
        self.items[key] = dict(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def update_item(self, Key, UpdateExpression=None, ExpressionAttributeValues=None, ConditionExpression=None):
        key = (Key["pk"], Key["sk"])
        if key not in self.items:
            raise AssertionError("missing item")
        self.items[key].update({
            "interviewStatus": ExpressionAttributeValues[":status"],
            "latestSubmissionId": ExpressionAttributeValues[":submissionId"],
            "submittedAt": ExpressionAttributeValues[":submittedAt"],
            "updatedAt": ExpressionAttributeValues[":updatedAt"],
        })
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


def _event(method="GET", job_id="job-123", candidate_id="cand-123", body=None, org_id="org-123", user_id="cand-user"):
    return {
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:org_id": org_id,
                        "sub": user_id,
                        "email": "candidate@example.com",
                        "custom:role": "candidate",
                    }
                }
            },
        },
        "pathParameters": {
            "jobId": job_id,
            "candidateId": candidate_id,
        },
        "body": json.dumps(body or {}),
    }


def _repo():
    table = FakeDynamoTable()
    table.items[("ORG#org-123#JOB#job-123", "CANDIDATE#cand-123")] = {
        "pk": "ORG#org-123#JOB#job-123",
        "sk": "CANDIDATE#cand-123",
        "orgId": "org-123",
        "jobId": "job-123",
        "candidateId": "cand-123",
        "name": "Asha Kumar",
        "email": "asha@example.com",
        "interviewStatus": "Interview Prepared",
        "questions": [
            "How did you design the Python APIs?",
            "How did you use AWS Lambda?",
            "How did you model DynamoDB data?",
            "Tell me about a delivery challenge.",
            "Why are you a fit for this role?",
        ],
        "questionKeywords": [["Python", "API"], ["Lambda"], ["DynamoDB"], [], ["AWS"]],
        "preparedAt": 1710000000,
    }
    return CandidateInterviewsRepository(table), table


def test_get_candidate_interview_returns_prepared_questions(monkeypatch):
    repo, _table = _repo()
    monkeypatch.setattr(candidate_interview, "_get_repository", lambda: repo)

    response = candidate_interview.handler(_event("GET"), None)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    questions = payload["interview"]["questions"]
    assert len(questions) == 5
    assert questions[0]["questionIndex"] == 0
    assert questions[0]["keywords"] == ["Python", "API"]


def test_submit_candidate_interview_stores_answers_and_integrity_signals(monkeypatch):
    repo, table = _repo()
    monkeypatch.setattr(candidate_interview, "_get_repository", lambda: repo)

    response = candidate_interview.handler(_event("POST", body={
        "consentAccepted": True,
        "answers": [
            {"questionIndex": 1, "answerText": "I used Lambda for async processing.", "durationSeconds": 61},
            {"questionIndex": 0, "answerText": "I designed REST APIs with clear boundaries.", "durationSeconds": 55},
        ],
        "integritySignals": {
            "tabSwitches": 1,
            "fullscreenExits": 0,
            "copyPasteAttempts": 2,
            "devtoolsAttempts": 0,
            "events": [{"type": "tab_switch", "questionIndex": 0, "timestamp": "2026-05-05T10:00:00Z"}],
        },
    }), None)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])
    submission = payload["submission"]
    assert submission["answerCount"] == 2
    assert submission["integritySignals"]["tabSwitches"] == 1
    assert submission["integritySignals"]["copyPasteAttempts"] == 2
    candidate = table.items[("ORG#org-123#JOB#job-123", "CANDIDATE#cand-123")]
    assert candidate["interviewStatus"] == "Interview Submitted"
    assert candidate["latestSubmissionId"] == submission["submissionId"]
    submission_items = [item for item in table.items.values() if item.get("entityType") == "InterviewSubmission"]
    assert len(submission_items) == 1
    assert [answer["questionIndex"] for answer in submission_items[0]["answers"]] == [0, 1]


def test_submit_candidate_interview_requires_consent(monkeypatch):
    repo, _table = _repo()
    monkeypatch.setattr(candidate_interview, "_get_repository", lambda: repo)

    response = candidate_interview.handler(_event("POST", body={
        "consentAccepted": False,
        "answers": [{"questionIndex": 0, "answerText": "Answer"}],
    }), None)

    assert response["statusCode"] == 400
    assert "consent" in json.loads(response["body"])["error"].lower()


def test_submit_candidate_interview_rejects_invalid_question_index(monkeypatch):
    repo, _table = _repo()
    monkeypatch.setattr(candidate_interview, "_get_repository", lambda: repo)

    response = candidate_interview.handler(_event("POST", body={
        "consentAccepted": True,
        "answers": [{"questionIndex": 99, "answerText": "Answer"}],
    }), None)

    assert response["statusCode"] == 400
    assert "questionIndex" in json.loads(response["body"])["error"]
