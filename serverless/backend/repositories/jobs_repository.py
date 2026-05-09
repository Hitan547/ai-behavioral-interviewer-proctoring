"""DynamoDB repository for job postings."""

from __future__ import annotations

import os
import time
import uuid
from decimal import Decimal
from typing import Any


class JobsRepository:
    def __init__(self, table: Any):
        self.table = table

    @classmethod
    def from_environment(cls) -> "JobsRepository":
        table_name = os.environ.get("TABLE_NAME")
        if not table_name:
            raise RuntimeError("TABLE_NAME environment variable is required.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 is required in AWS Lambda runtime.") from exc
        table = boto3.resource("dynamodb").Table(table_name)
        return cls(table)

    def create_job(
        self,
        *,
        org_id: str,
        recruiter_id: str,
        title: str,
        jd_text: str,
        min_pass_score: int = 60,
        open_positions: int = 10,
        shortlist_threshold: float = 7,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_epoch_seconds()
        job_id = str(uuid.uuid4())
        item = {
            "pk": _org_pk(org_id),
            "sk": _job_sk(job_id),
            "entityType": "JobPosting",
            "orgId": org_id,
            "jobId": job_id,
            "title": title,
            "jdText": jd_text,
            "minPassScore": min_pass_score,
            "openPositions": open_positions,
            "shortlistThreshold": Decimal(str(round(shortlist_threshold, 2))),
            "deadline": deadline,
            "status": "Active",
            "createdBy": recruiter_id,
            "createdAt": now,
            "updatedAt": now,
        }
        self.table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return _public_job(item)

    def list_jobs(self, org_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": _org_pk(org_id),
                ":prefix": "JOB#",
            },
            ScanIndexForward=False,
        )
        items = response.get("Items", [])
        return [_public_job(item) for item in items]

    def get_job(self, org_id: str, job_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"pk": _org_pk(org_id), "sk": _job_sk(job_id)})
        item = response.get("Item")
        return _public_job(item) if item else None

    def update_job_status(self, org_id: str, job_id: str, status: str) -> dict[str, Any] | None:
        now = _utc_epoch_seconds()
        response = self.table.update_item(
            Key={"pk": _org_pk(org_id), "sk": _job_sk(job_id)},
            UpdateExpression="SET #status = :status, updatedAt = :updatedAt",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status, ":updatedAt": now},
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
            ReturnValues="ALL_NEW",
        )
        item = response.get("Attributes")
        return _public_job(item) if item else None

    def get_job_stats(self, org_id: str, job_id: str) -> dict[str, int]:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"ORG#{org_id}#JOB#{job_id}",
                ":prefix": "CANDIDATE#",
            },
        )
        stats = {
            "total": 0,
            "invited": 0,
            "inProgress": 0,
            "completed": 0,
            "passed": 0,
            "belowThreshold": 0,
            "expired": 0,
        }
        for item in response.get("Items", []):
            stats["total"] += 1
            status = str(item.get("interviewStatus", ""))
            if status == "Invited":
                stats["invited"] += 1
            elif status == "In Progress":
                stats["inProgress"] += 1
            elif status in {"Completed", "Interview Submitted", "Scored"}:
                stats["completed"] += 1
            elif status == "Passed":
                stats["passed"] += 1
            elif status == "Below Threshold":
                stats["belowThreshold"] += 1
            elif status == "Expired":
                stats["expired"] += 1
        return stats


def _org_pk(org_id: str) -> str:
    return f"ORG#{org_id}"


def _job_sk(job_id: str) -> str:
    return f"JOB#{job_id}"


def _utc_epoch_seconds() -> int:
    return int(time.time())


def _public_job(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "orgId": item["orgId"],
        "jobId": item["jobId"],
        "title": item["title"],
        "jdText": item["jdText"],
        "minPassScore": item.get("minPassScore", 60),
        "openPositions": item.get("openPositions", 10),
        "shortlistThreshold": item.get("shortlistThreshold", 7),
        "deadline": item.get("deadline"),
        "status": item.get("status", "Active"),
        "createdBy": item.get("createdBy"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
