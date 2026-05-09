import json
import os
import sys
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"
os.environ["SCORING_WORKFLOW_ARN"] = "arn:aws:states:us-east-1:123:stateMachine:psysense-dev-scoring"

from handlers import scoring, scoring_worker
from repositories.scoring_repository import ScoringRepository
from services import scoring_engine


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
        item = self.items[key]
        if ":score" in ExpressionAttributeValues:
            item.update({
                "interviewStatus": ExpressionAttributeValues[":status"],
                "latestResultScore": ExpressionAttributeValues[":score"],
                "latestRecommendation": ExpressionAttributeValues[":recommendation"],
                "latestAssessmentStatus": ExpressionAttributeValues[":assessmentStatus"],
                "latestResultAt": ExpressionAttributeValues[":resultAt"],
                "updatedAt": ExpressionAttributeValues[":updatedAt"],
            })
        if ":key" in ExpressionAttributeValues:
            item.update({
                "reportS3Bucket": ExpressionAttributeValues[":bucket"],
                "reportS3Key": ExpressionAttributeValues[":key"],
                "reportContentType": ExpressionAttributeValues[":contentType"],
                "reportGeneratedAt": ExpressionAttributeValues[":generatedAt"],
            })
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def query(self, KeyConditionExpression=None, ExpressionAttributeValues=None, ScanIndexForward=True, Limit=None):
        pk = ExpressionAttributeValues[":pk"]
        prefix = ExpressionAttributeValues[":prefix"]
        found = [
            item for (item_pk, item_sk), item in self.items.items()
            if item_pk == pk and item_sk.startswith(prefix)
        ]
        found.sort(key=lambda item: item["sk"], reverse=not ScanIndexForward)
        if Limit:
            found = found[:Limit]
        return {"Items": found}


class FakeStepFunctionsClient:
    def __init__(self):
        self.calls = []

    def start_execution(self, stateMachineArn, input):
        self.calls.append({"stateMachineArn": stateMachineArn, "input": json.loads(input)})
        return {
            "executionArn": "arn:aws:states:us-east-1:123:execution:workflow:test",
            "startDate": "2026-05-05T10:00:00+00:00",
        }


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.presigned = []

    def put_object(self, Bucket, Key, Body, ContentType, ServerSideEncryption):
        self.objects[(Bucket, Key)] = {
            "Body": Body,
            "ContentType": ContentType,
            "ServerSideEncryption": ServerSideEncryption,
        }
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn, HttpMethod):
        self.presigned.append({
            "ClientMethod": ClientMethod,
            "Params": Params,
            "ExpiresIn": ExpiresIn,
            "HttpMethod": HttpMethod,
        })
        return f"https://download.example.test/{Params['Key']}"


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
        "pathParameters": {"jobId": job_id, "candidateId": candidate_id},
        "body": "{}",
    }


def _repo():
    table = FakeDynamoTable()
    s3 = FakeS3Client()
    table.items[("ORG#org-123", "JOB#job-123")] = {
        "pk": "ORG#org-123",
        "sk": "JOB#job-123",
        "orgId": "org-123",
        "jobId": "job-123",
        "title": "Backend Engineer",
        "jdText": "Build Python APIs with AWS Lambda and DynamoDB.",
    }
    table.items[("ORG#org-123#JOB#job-123", "CANDIDATE#cand-123")] = {
        "pk": "ORG#org-123#JOB#job-123",
        "sk": "CANDIDATE#cand-123",
        "orgId": "org-123",
        "jobId": "job-123",
        "candidateId": "cand-123",
        "name": "Asha Kumar",
        "interviewStatus": "Interview Submitted",
        "questions": [
            "How did you design Python APIs?",
            "How did you use AWS Lambda?",
        ],
    }
    table.items[("ORG#org-123#JOB#job-123", "SUBMISSION#cand-123#1710000000")] = {
        "pk": "ORG#org-123#JOB#job-123",
        "sk": "SUBMISSION#cand-123#1710000000",
        "entityType": "InterviewSubmission",
        "orgId": "org-123",
        "jobId": "job-123",
        "candidateId": "cand-123",
        "submissionId": "cand-123-1710000000",
        "answers": [
            {
                "questionIndex": 0,
                "answerText": "I designed Python REST APIs with clear service boundaries and measured impact.",
            },
            {
                "questionIndex": 1,
                "answerText": "I used AWS Lambda for serverless async processing because it reduced operations.",
            },
        ],
        "integritySignals": {
            "tabSwitches": 1,
            "fullscreenExits": 0,
            "copyPasteAttempts": 0,
            "devtoolsAttempts": 0,
            "events": [],
        },
    }
    return ScoringRepository(table, s3, "psysense-dev-artifacts"), table, s3


def test_start_scoring_workflow(monkeypatch):
    repo, _table, _s3 = _repo()
    sf_client = FakeStepFunctionsClient()
    monkeypatch.setattr(scoring, "_get_repository", lambda: repo)
    monkeypatch.setattr(scoring, "_get_stepfunctions_client", lambda: sf_client)

    response = scoring.handler(_event("POST"), None)

    assert response["statusCode"] == 202
    assert sf_client.calls[0]["stateMachineArn"] == os.environ["SCORING_WORKFLOW_ARN"]
    assert sf_client.calls[0]["input"]["candidateId"] == "cand-123"


def test_scoring_worker_saves_result_and_updates_candidate(monkeypatch):
    repo, table, s3 = _repo()
    monkeypatch.setattr(scoring_worker, "_get_repository", lambda: repo)

    output = scoring_worker.handler({
        "orgId": "org-123",
        "jobId": "job-123",
        "candidateId": "cand-123",
    }, None)

    result = output["result"]
    assert result["finalScore"] > 0
    assert result["baseScore"] >= result["finalScore"]
    assert result["recommendation"] in {"Strong Fit", "Needs Review", "Not Recommended", "Manual Review Required"}
    assert len(result["perQuestion"]) == 2
    candidate = table.items[("ORG#org-123#JOB#job-123", "CANDIDATE#cand-123")]
    assert candidate["interviewStatus"] == "Scored"
    assert candidate["latestResultScore"] == result["finalScore"]
    assert result["reportS3Key"].startswith("reports/org-123/job-123/cand-123/")
    assert next(iter(s3.objects.values()))["ContentType"] == "application/pdf"
    assert next(iter(s3.objects.values()))["Body"].startswith(b"%PDF-")


def test_passing_answer_with_high_integrity_risk_requires_manual_review(monkeypatch):
    def fake_score(index, question, answer, jd_text):
        return {
            "questionIndex": index,
            "question": question,
            "answerText": answer,
            "answered": True,
            "score": 80,
            "verdict": "Strong",
            "summary": "Strong role signal.",
            "method": "test",
        }

    monkeypatch.setattr(scoring_engine, "_score_single_answer", fake_score)
    result = scoring_engine.score_interview(
        job={"title": "ML Engineer", "jdText": "Machine learning", "minPassScore": 60},
        candidate={"name": "Candidate", "questions": ["Tell me about ML deployment."]},
        submission={
            "answers": [{"questionIndex": 0, "answerText": "I deployed several ML models."}],
            "integritySignals": {"faceNotDetected": 41},
        },
    )

    assert result["baseScore"] == 80
    assert result["finalScore"] == 65
    assert result["assessmentStatus"] == "Review Required"
    assert result["recommendation"] == "Manual Review Required"


def test_get_scoring_result(monkeypatch):
    repo, _table, _s3 = _repo()
    monkeypatch.setattr(scoring_worker, "_get_repository", lambda: repo)
    scoring_worker.handler({"orgId": "org-123", "jobId": "job-123", "candidateId": "cand-123"}, None)
    monkeypatch.setattr(scoring, "_get_repository", lambda: repo)

    response = scoring.handler(_event("GET"), None)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert payload["result"]["candidateId"] == "cand-123"
    assert payload["result"]["finalScore"] > 0
    assert payload["result"]["reportDownload"]["url"].startswith("https://download.example.test/")
    assert payload["result"]["reportDownload"]["contentType"] == "application/pdf"


def test_start_scoring_requires_submission(monkeypatch):
    repo, table, _s3 = _repo()
    del table.items[("ORG#org-123#JOB#job-123", "SUBMISSION#cand-123#1710000000")]
    monkeypatch.setattr(scoring, "_get_repository", lambda: repo)

    response = scoring.handler(_event("POST"), None)

    assert response["statusCode"] == 400
    assert "submitted" in json.loads(response["body"])["error"]
