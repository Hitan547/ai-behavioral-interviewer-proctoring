"""DynamoDB + S3 repository for candidate metadata and resume uploads."""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any


class CandidatesRepository:
    def __init__(self, table: Any, s3_client: Any, artifact_bucket: str):
        self.table = table
        self.s3_client = s3_client
        self.artifact_bucket = artifact_bucket

    @classmethod
    def from_environment(cls) -> "CandidatesRepository":
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

    def create_candidate(
        self,
        *,
        org_id: str,
        job_id: str,
        recruiter_id: str,
        name: str,
        email: str,
        resume_filename: str,
        resume_content_type: str,
        college_name: str | None = None,
        department: str | None = None,
        graduation_year: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_epoch_seconds()
        candidate_id = str(uuid.uuid4())
        resume_key = _resume_key(org_id, job_id, candidate_id, resume_filename)
        item = {
            "pk": _job_candidate_pk(org_id, job_id),
            "sk": _candidate_sk(candidate_id),
            "entityType": "CandidateProfile",
            "orgId": org_id,
            "jobId": job_id,
            "candidateId": candidate_id,
            "name": name,
            "email": email,
            "resumeFilename": resume_filename,
            "resumeContentType": resume_content_type,
            "resumeS3Bucket": self.artifact_bucket,
            "resumeS3Key": resume_key,
            "interviewStatus": "Resume Upload Pending",
            "shortlisted": False,
            "createdBy": recruiter_id,
            "createdAt": now,
            "updatedAt": now,
        }
        _put_optional_source_fields(
            item,
            college_name=college_name,
            department=department,
            graduation_year=graduation_year,
        )
        self.table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        upload_url = self.create_resume_upload_url(
            resume_key=resume_key,
            content_type=resume_content_type,
        )
        return {
            "candidate": _public_candidate(item),
            "resumeUpload": {
                "method": "PUT",
                "url": upload_url,
                "bucket": self.artifact_bucket,
                "key": resume_key,
                "expiresIn": 900,
                "headers": {
                    "Content-Type": resume_content_type,
                },
            },
        }

    def list_candidates(self, org_id: str, job_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": _job_candidate_pk(org_id, job_id),
                ":prefix": "CANDIDATE#",
            },
            ScanIndexForward=False,
        )
        return [_public_candidate(item) for item in response.get("Items", [])]

    def update_candidate(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        name: str | None = None,
        email: str | None = None,
        college_name: str | None = None,
        department: str | None = None,
        graduation_year: str | None = None,
        shortlisted: bool | None = None,
    ) -> dict[str, Any] | None:
        now = _utc_epoch_seconds()
        update_parts = ["updatedAt = :updatedAt"]
        values: dict[str, Any] = {":updatedAt": now}
        names: dict[str, str] = {}

        if name is not None:
            update_parts.append("#name = :name")
            names["#name"] = "name"
            values[":name"] = name
        if email is not None:
            update_parts.append("email = :email")
            values[":email"] = email
        if college_name is not None:
            update_parts.append("collegeName = :collegeName")
            values[":collegeName"] = college_name
        if department is not None:
            update_parts.append("department = :department")
            values[":department"] = department
        if graduation_year is not None:
            update_parts.append("graduationYear = :graduationYear")
            values[":graduationYear"] = graduation_year
        if shortlisted is not None:
            update_parts.append("shortlisted = :shortlisted")
            values[":shortlisted"] = shortlisted
            if shortlisted:
                update_parts.append("shortlistedAt = :shortlistedAt")
                values[":shortlistedAt"] = now
            else:
                update_parts.append("shortlistedAt = :shortlistedAt")
                values[":shortlistedAt"] = 0

        response = self.table.update_item(
            Key={
                "pk": _job_candidate_pk(org_id, job_id),
                "sk": _candidate_sk(candidate_id),
            },
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeValues=values,
            **({"ExpressionAttributeNames": names} if names else {}),
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
            ReturnValues="ALL_NEW",
        )
        item = response.get("Attributes")
        return _public_candidate(item) if item else None

    def create_resume_upload_url(self, *, resume_key: str, content_type: str) -> str:
        return self.s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.artifact_bucket,
                "Key": resume_key,
                "ContentType": content_type,
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )


def _job_candidate_pk(org_id: str, job_id: str) -> str:
    return f"ORG#{org_id}#JOB#{job_id}"


def _candidate_sk(candidate_id: str) -> str:
    return f"CANDIDATE#{candidate_id}"


def _utc_epoch_seconds() -> int:
    return int(time.time())


def _resume_key(org_id: str, job_id: str, candidate_id: str, filename: str) -> str:
    safe_filename = _safe_filename(filename or "resume.pdf")
    return f"resumes/{org_id}/{job_id}/{candidate_id}/{safe_filename}"


def _safe_filename(filename: str) -> str:
    base = filename.split("/")[-1].split("\\")[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    return base or "resume.pdf"


def _put_optional_source_fields(
    item: dict[str, Any],
    *,
    college_name: str | None,
    department: str | None,
    graduation_year: str | None,
) -> None:
    if college_name:
        item["collegeName"] = college_name
    if department:
        item["department"] = department
    if graduation_year:
        item["graduationYear"] = graduation_year


def _public_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "orgId": item["orgId"],
        "jobId": item["jobId"],
        "candidateId": item["candidateId"],
        "name": item["name"],
        "email": item["email"],
        "collegeName": item.get("collegeName"),
        "department": item.get("department"),
        "graduationYear": item.get("graduationYear"),
        "resumeFilename": item.get("resumeFilename"),
        "resumeS3Key": item.get("resumeS3Key"),
        "matchScore": item.get("matchScore"),
        "matchReason": item.get("matchReason"),
        "shortlisted": bool(item.get("shortlisted", False)),
        "shortlistedAt": item.get("shortlistedAt"),
        "inviteSentAt": item.get("inviteSentAt"),
        "interviewStatus": item.get("interviewStatus", "Resume Upload Pending"),
        "submittedAt": item.get("submittedAt"),
        "startedAt": item.get("startedAt"),
        "latestSubmissionId": item.get("latestSubmissionId"),
        "latestResultScore": item.get("latestResultScore"),
        "latestRecommendation": item.get("latestRecommendation"),
        "latestAssessmentStatus": item.get("latestAssessmentStatus"),
        "latestIntegrityRiskLevel": item.get("latestIntegrityRiskLevel"),
        "latestIntegrityRiskScore": item.get("latestIntegrityRiskScore"),
        "latestIntegrityPenalty": item.get("latestIntegrityPenalty"),
        "latestResultAt": item.get("latestResultAt"),
        "latestReportGeneratedAt": item.get("latestReportGeneratedAt"),
        "retestCount": item.get("retestCount"),
        "lastRetestAt": item.get("lastRetestAt"),
        "createdBy": item.get("createdBy"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }
