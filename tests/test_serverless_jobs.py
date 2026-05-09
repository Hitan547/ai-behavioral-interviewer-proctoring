import json
import os
import sys
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from handlers import jobs
from repositories.jobs_repository import JobsRepository


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


def _event(method, body=None, org_id="org-123", user_id="user-123"):
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
        "body": json.dumps(body or {}),
    }


def test_create_job_writes_tenant_scoped_item(monkeypatch):
    table = FakeDynamoTable()
    monkeypatch.setattr(jobs, "_get_repository", lambda: JobsRepository(table))

    response = jobs.handler(_event("POST", {
        "title": "Backend Engineer",
        "jdText": "Build reliable APIs and services.",
        "minPassScore": 70,
    }), None)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])
    assert payload["job"]["orgId"] == "org-123"
    assert payload["job"]["title"] == "Backend Engineer"
    assert len(table.items) == 1
    stored = next(iter(table.items.values()))
    assert stored["pk"] == "ORG#org-123"
    assert stored["sk"].startswith("JOB#")


def test_list_jobs_returns_only_current_org(monkeypatch):
    table = FakeDynamoTable()
    repo = JobsRepository(table)
    repo.create_job(
        org_id="org-123",
        recruiter_id="user-123",
        title="Visible Job",
        jd_text="Visible JD",
    )
    repo.create_job(
        org_id="other-org",
        recruiter_id="user-999",
        title="Hidden Job",
        jd_text="Hidden JD",
    )
    monkeypatch.setattr(jobs, "_get_repository", lambda: repo)

    response = jobs.handler(_event("GET"), None)

    assert response["statusCode"] == 200
    payload = json.loads(response["body"])
    assert [job["title"] for job in payload["jobs"]] == ["Visible Job"]


def test_create_job_requires_title_and_jd(monkeypatch):
    table = FakeDynamoTable()
    monkeypatch.setattr(jobs, "_get_repository", lambda: JobsRepository(table))

    response = jobs.handler(_event("POST", {"title": "", "jdText": ""}), None)

    assert response["statusCode"] == 400
    assert "Job title is required" in json.loads(response["body"])["error"]


def test_missing_org_claim_is_unauthorized(monkeypatch):
    table = FakeDynamoTable()
    monkeypatch.setattr(jobs, "_get_repository", lambda: JobsRepository(table))

    response = jobs.handler(_event("GET", org_id=""), None)

    assert response["statusCode"] == 401
    assert "org_id" in json.loads(response["body"])["error"]
