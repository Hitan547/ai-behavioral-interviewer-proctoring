"""DynamoDB repository for interview scoring and recruiter results."""

from __future__ import annotations

import os
import time
from typing import Any


class ScoringRepository:
    def __init__(self, table: Any, s3_client: Any | None = None, artifact_bucket: str = ""):
        self.table = table
        self.s3_client = s3_client
        self.artifact_bucket = artifact_bucket

    @classmethod
    def from_environment(cls) -> "ScoringRepository":
        table_name = os.environ.get("TABLE_NAME")
        artifact_bucket = os.environ.get("ARTIFACT_BUCKET", "")
        if not table_name:
            raise RuntimeError("TABLE_NAME environment variable is required.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 is required in AWS Lambda runtime.") from exc
        table = boto3.resource("dynamodb").Table(table_name)
        s3_client = boto3.client("s3")
        return cls(table, s3_client, artifact_bucket)

    def get_job(self, org_id: str, job_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"pk": _org_pk(org_id), "sk": _job_sk(job_id)})
        return response.get("Item")

    def get_candidate(self, org_id: str, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={"pk": _job_candidate_pk(org_id, job_id), "sk": _candidate_sk(candidate_id)}
        )
        return response.get("Item")

    def get_latest_submission(self, org_id: str, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": _job_candidate_pk(org_id, job_id),
                ":prefix": f"SUBMISSION#{candidate_id}#",
            },
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        return items[0] if items else None

    def get_latest_result(self, org_id: str, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": _job_candidate_pk(org_id, job_id),
                ":prefix": f"RESULT#{candidate_id}#",
            },
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        return _public_result(items[0]) if items else None

    def save_scoring_result(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        submission_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_epoch_seconds()
        item = {
            "pk": _job_candidate_pk(org_id, job_id),
            "sk": _result_sk(candidate_id, now),
            "entityType": "ScoringResult",
            "orgId": org_id,
            "jobId": job_id,
            "candidateId": candidate_id,
            "submissionId": submission_id,
            "finalScore": result["finalScore"],
            "recommendation": result["recommendation"],
            "integrityRisk": result["integrityRisk"],
            "perQuestion": result["perQuestion"],
            "summary": result["summary"],
            "createdAt": now,
        }
        self.table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        self.table.update_item(
            Key={"pk": _job_candidate_pk(org_id, job_id), "sk": _candidate_sk(candidate_id)},
            UpdateExpression=(
                "SET interviewStatus = :status, latestResultScore = :score, "
                "latestRecommendation = :recommendation, latestResultAt = :resultAt, updatedAt = :updatedAt"
            ),
            ExpressionAttributeValues={
                ":status": "Scored",
                ":score": result["finalScore"],
                ":recommendation": result["recommendation"],
                ":resultAt": now,
                ":updatedAt": now,
            },
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
        )
        return _public_result(item)

    def save_report_pdf(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        result: dict[str, Any],
        pdf_bytes: bytes,
    ) -> dict[str, Any]:
        if not self.s3_client:
            raise RuntimeError("S3 client is required to save report artifacts.")
        if not self.artifact_bucket:
            raise RuntimeError("ARTIFACT_BUCKET environment variable is required.")

        created_at = int(result.get("createdAt") or _utc_epoch_seconds())
        report_key = f"reports/{org_id}/{job_id}/{candidate_id}/report-{created_at}.pdf"
        self.s3_client.put_object(
            Bucket=self.artifact_bucket,
            Key=report_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )
        self.table.update_item(
            Key={
                "pk": _job_candidate_pk(org_id, job_id),
                "sk": _result_sk(candidate_id, created_at),
            },
            UpdateExpression=(
                "SET reportS3Bucket = :bucket, reportS3Key = :key, "
                "reportContentType = :contentType, reportGeneratedAt = :generatedAt"
            ),
            ExpressionAttributeValues={
                ":bucket": self.artifact_bucket,
                ":key": report_key,
                ":contentType": "application/pdf",
                ":generatedAt": _utc_epoch_seconds(),
            },
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
        )
        enriched = dict(result)
        enriched.update({
            "reportS3Bucket": self.artifact_bucket,
            "reportS3Key": report_key,
            "reportContentType": "application/pdf",
        })
        return enriched

    def create_report_download_url(self, result: dict[str, Any], expires_in: int = 900) -> str | None:
        if not self.s3_client:
            return None
        bucket = result.get("reportS3Bucket")
        key = result.get("reportS3Key")
        if not bucket or not key:
            return None
        return self.s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ResponseContentType": result.get("reportContentType", "application/pdf"),
            },
            ExpiresIn=expires_in,
            HttpMethod="GET",
        )


def _org_pk(org_id: str) -> str:
    return f"ORG#{org_id}"


def _job_sk(job_id: str) -> str:
    return f"JOB#{job_id}"


def _job_candidate_pk(org_id: str, job_id: str) -> str:
    return f"ORG#{org_id}#JOB#{job_id}"


def _candidate_sk(candidate_id: str) -> str:
    return f"CANDIDATE#{candidate_id}"


def _result_sk(candidate_id: str, created_at: int) -> str:
    return f"RESULT#{candidate_id}#{created_at}"


def _utc_epoch_seconds() -> int:
    return int(time.time())


def _public_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "orgId": item["orgId"],
        "jobId": item["jobId"],
        "candidateId": item["candidateId"],
        "submissionId": item.get("submissionId"),
        "finalScore": item.get("finalScore", 0),
        "recommendation": item.get("recommendation", "Needs Review"),
        "integrityRisk": item.get("integrityRisk", {}),
        "perQuestion": item.get("perQuestion", []),
        "summary": item.get("summary", ""),
        "reportS3Bucket": item.get("reportS3Bucket"),
        "reportS3Key": item.get("reportS3Key"),
        "reportContentType": item.get("reportContentType"),
        "reportGeneratedAt": item.get("reportGeneratedAt"),
        "createdAt": item.get("createdAt"),
    }
