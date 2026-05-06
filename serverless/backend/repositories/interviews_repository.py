"""DynamoDB + S3 repository for interview preparation."""

from __future__ import annotations

import os
import time
from typing import Any


class InterviewsRepository:
    def __init__(self, table: Any, s3_client: Any, artifact_bucket: str):
        self.table = table
        self.s3_client = s3_client
        self.artifact_bucket = artifact_bucket

    @classmethod
    def from_environment(cls) -> "InterviewsRepository":
        table_name = os.environ.get("TABLE_NAME")
        artifact_bucket = os.environ.get("ARTIFACT_BUCKET")
        if not table_name:
            raise RuntimeError("TABLE_NAME environment variable is required.")
        if not artifact_bucket:
            raise RuntimeError("ARTIFACT_BUCKET environment variable is required.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 is required in AWS Lambda runtime.") from exc
        table = boto3.resource("dynamodb").Table(table_name)
        s3_client = boto3.client("s3")
        return cls(table, s3_client, artifact_bucket)

    def get_job(self, org_id: str, job_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={
                "pk": _org_pk(org_id),
                "sk": _job_sk(job_id),
            }
        )
        return response.get("Item")

    def get_candidate(self, org_id: str, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={
                "pk": _job_candidate_pk(org_id, job_id),
                "sk": _candidate_sk(candidate_id),
            }
        )
        return response.get("Item")

    def get_resume_bytes(self, candidate: dict[str, Any]) -> bytes:
        bucket = candidate.get("resumeS3Bucket") or self.artifact_bucket
        key = candidate.get("resumeS3Key")
        if not key:
            raise ValueError("Candidate resume S3 key is missing.")
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        return body.read()

    def save_prepared_questions(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        questions: list[str],
        question_keywords: list[list[str]],
        vocab: dict[str, Any],
        resume_text: str,
        prepared_by: str,
    ) -> dict[str, Any]:
        now = _utc_epoch_seconds()
        key = {
            "pk": _job_candidate_pk(org_id, job_id),
            "sk": _candidate_sk(candidate_id),
        }
        self.table.update_item(
            Key=key,
            UpdateExpression=(
                "SET interviewStatus = :status, #questions = :questions, "
                "questionKeywords = :keywords, #vocab = :vocab, resumeTextPreview = :preview, "
                "preparedBy = :preparedBy, preparedAt = :preparedAt, updatedAt = :updatedAt"
            ),
            ExpressionAttributeNames={
                "#questions": "questions",
                "#vocab": "vocab",
            },
            ExpressionAttributeValues={
                ":status": "Interview Prepared",
                ":questions": questions,
                ":keywords": question_keywords,
                ":vocab": vocab,
                ":preview": (resume_text or "")[:2000],
                ":preparedBy": prepared_by,
                ":preparedAt": now,
                ":updatedAt": now,
            },
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
        )
        return {
            "candidateId": candidate_id,
            "jobId": job_id,
            "orgId": org_id,
            "interviewStatus": "Interview Prepared",
            "questions": questions,
            "questionKeywords": question_keywords,
            "vocab": vocab,
            "preparedAt": now,
        }


def _org_pk(org_id: str) -> str:
    return f"ORG#{org_id}"


def _job_sk(job_id: str) -> str:
    return f"JOB#{job_id}"


def _job_candidate_pk(org_id: str, job_id: str) -> str:
    return f"ORG#{org_id}#JOB#{job_id}"


def _candidate_sk(candidate_id: str) -> str:
    return f"CANDIDATE#{candidate_id}"


def _utc_epoch_seconds() -> int:
    return int(time.time())
