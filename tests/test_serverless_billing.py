import json
import os
import sys
import time
from pathlib import Path

SERVERLESS_BACKEND = Path(__file__).resolve().parents[1] / "serverless" / "backend"
sys.path.insert(0, str(SERVERLESS_BACKEND))
os.environ["ENVIRONMENT"] = "test"

from handlers import billing
from repositories.billing_repository import BillingRepository


class FakeDynamoTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression=None):
        self.items[(Item["pk"], Item["sk"])] = dict(Item)
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    def get_item(self, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": dict(item)} if item else {}

    def query(self, KeyConditionExpression=None, ExpressionAttributeValues=None, ScanIndexForward=True):
        pk = ExpressionAttributeValues[":pk"]
        prefix = ExpressionAttributeValues[":prefix"]
        found = [
            dict(item)
            for (item_pk, item_sk), item in self.items.items()
            if item_pk == pk and item_sk.startswith(prefix)
        ]
        found.sort(key=lambda item: item["sk"], reverse=not ScanIndexForward)
        return {"Items": found}


def _event(method="GET", org_id="org-123", role="recruiter"):
    return {
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:org_id": org_id,
                        "sub": "user-123",
                        "email": "recruiter@example.com",
                        "custom:role": role,
                    }
                }
            },
        },
    }


def test_billing_summary_counts_current_month_interviews():
    table = FakeDynamoTable()
    now = int(time.time())
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "PROFILE",
        "entityType": "Organization",
        "orgId": "org-123",
        "orgName": "Test Org",
        "subscriptionPlan": "starter",
        "currentMonth": time.strftime("%Y-%m", time.gmtime(now)),
        "trialExpiresAt": now + 1000,
        "createdAt": now,
    })
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "JOB#job-1",
        "entityType": "JobPosting",
        "orgId": "org-123",
        "jobId": "job-1",
    })
    table.put_item(Item={
        "pk": "ORG#org-123#JOB#job-1",
        "sk": "CANDIDATE#candidate-1",
        "entityType": "CandidateProfile",
        "orgId": "org-123",
        "jobId": "job-1",
        "candidateId": "candidate-1",
        "interviewStatus": "Completed",
        "submittedAt": now,
    })

    summary = BillingRepository(table).get_billing_summary("org-123")

    assert summary["currentPlan"]["id"] == "starter"
    assert summary["usage"]["used"] == 1
    assert summary["usage"]["limit"] == 100
    assert summary["usage"]["remaining"] == 99


def test_billing_summary_counts_invited_candidates_as_reserved_interviews():
    table = FakeDynamoTable()
    now = int(time.time())
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "PROFILE",
        "entityType": "Organization",
        "orgId": "org-123",
        "orgName": "Test Org",
        "subscriptionPlan": "trial",
        "currentMonth": time.strftime("%Y-%m", time.gmtime(now)),
        "trialExpiresAt": now + 1000,
        "createdAt": now,
    })
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "JOB#job-1",
        "entityType": "JobPosting",
        "orgId": "org-123",
        "jobId": "job-1",
    })
    table.put_item(Item={
        "pk": "ORG#org-123#JOB#job-1",
        "sk": "CANDIDATE#candidate-1",
        "entityType": "CandidateProfile",
        "orgId": "org-123",
        "jobId": "job-1",
        "candidateId": "candidate-1",
        "interviewStatus": "Invited",
        "inviteSentAt": now,
    })

    summary = BillingRepository(table).get_billing_summary("org-123")

    assert summary["usage"]["used"] == 1
    assert summary["usage"]["remaining"] == 49


def test_invite_quota_blocks_when_monthly_limit_is_reached():
    table = FakeDynamoTable()
    now = int(time.time())
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "PROFILE",
        "entityType": "Organization",
        "orgId": "org-123",
        "orgName": "Test Org",
        "subscriptionPlan": "trial",
        "currentMonth": time.strftime("%Y-%m", time.gmtime(now)),
        "trialExpiresAt": now + 1000,
        "usedInterviews": 50,
        "createdAt": now,
    })

    quota = BillingRepository(table).check_invite_quota("org-123")

    assert quota["allowed"] is False
    assert quota["reason"] == "quota_exceeded"


def test_invite_quota_allows_enterprise_without_limit():
    table = FakeDynamoTable()
    now = int(time.time())
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "PROFILE",
        "entityType": "Organization",
        "orgId": "org-123",
        "orgName": "Test Org",
        "subscriptionPlan": "enterprise",
        "currentMonth": time.strftime("%Y-%m", time.gmtime(now)),
        "usedInterviews": 999,
        "createdAt": now,
    })

    quota = BillingRepository(table).check_invite_quota("org-123")

    assert quota["allowed"] is True


def test_billing_handler_rejects_candidate_role(monkeypatch):
    table = FakeDynamoTable()
    monkeypatch.setattr(billing, "_get_repository", lambda: BillingRepository(table))

    response = billing.handler(_event(role="candidate"), None)

    assert response["statusCode"] == 403
    assert "Only recruiters" in json.loads(response["body"])["error"]


def test_billing_handler_returns_summary(monkeypatch):
    table = FakeDynamoTable()
    now = int(time.time())
    table.put_item(Item={
        "pk": "ORG#org-123",
        "sk": "PROFILE",
        "entityType": "Organization",
        "orgId": "org-123",
        "orgName": "Test Org",
        "subscriptionPlan": "trial",
        "currentMonth": time.strftime("%Y-%m", time.gmtime(now)),
        "trialExpiresAt": now + 1000,
        "createdAt": now,
    })
    monkeypatch.setattr(billing, "_get_repository", lambda: BillingRepository(table))

    response = billing.handler(_event(), None)
    payload = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert payload["billing"]["organization"]["orgName"] == "Test Org"
    assert payload["billing"]["currentPlan"]["id"] == "trial"
