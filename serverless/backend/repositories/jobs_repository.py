"""DynamoDB repository for job postings."""

from __future__ import annotations

import os
import time
import uuid
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
        "deadline": item.get("deadline"),
        "status": item.get("status", "Active"),
        "createdBy": item.get("createdBy"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }

