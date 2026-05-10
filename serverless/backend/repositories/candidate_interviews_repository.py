"""DynamoDB repository for candidate interview delivery and submissions."""

from __future__ import annotations

import os
import re
import time
from decimal import Decimal
from typing import Any


class CandidateInterviewsRepository:
    def __init__(self, table: Any, s3_client: Any | None = None, artifact_bucket: str = ""):
        self.table = table
        self.s3_client = s3_client
        self.artifact_bucket = artifact_bucket

    @classmethod
    def from_environment(cls) -> "CandidateInterviewsRepository":
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

    def get_candidate(self, org_id: str, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(
            Key={
                "pk": _job_candidate_pk(org_id, job_id),
                "sk": _candidate_sk(candidate_id),
            }
        )
        return response.get("Item")

    def find_candidate_by_session_token(self, *, job_id: str, candidate_id: str, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        scan_kwargs: dict[str, Any] = {}
        while True:
            response = self.table.scan(**scan_kwargs)
            for item in response.get("Items", []):
                if (
                    str(item.get("entityType", "")) == "CandidateProfile"
                    and str(item.get("jobId", "")) == job_id
                    and str(item.get("candidateId", "")) == candidate_id
                    and str(item.get("candidateSessionToken", "")) == token
                ):
                    return item
            if "LastEvaluatedKey" not in response:
                return None
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def get_prepared_interview(self, org_id: str, job_id: str, candidate_id: str) -> dict[str, Any] | None:
        candidate = self.get_candidate(org_id, job_id, candidate_id)
        if not candidate:
            return None

        questions = candidate.get("questions") or []
        if not isinstance(questions, list) or not questions:
            raise ValueError("Interview questions have not been prepared for this candidate.")

        keywords = candidate.get("questionKeywords") or []
        if not isinstance(keywords, list):
            keywords = []

        return {
            "orgId": org_id,
            "jobId": job_id,
            "candidateId": candidate_id,
            "candidateName": candidate.get("name"),
            "interviewStatus": candidate.get("interviewStatus", "Interview Prepared"),
            "questions": [
                {
                    "questionIndex": index,
                    "question": str(question),
                    "keywords": keywords[index] if index < len(keywords) and isinstance(keywords[index], list) else [],
                }
                for index, question in enumerate(questions)
            ],
            "preparedAt": candidate.get("preparedAt"),
        }

    def mark_interview_started(self, org_id: str, job_id: str, candidate_id: str) -> None:
        now = _utc_epoch_seconds()
        self.table.update_item(
            Key={
                "pk": _job_candidate_pk(org_id, job_id),
                "sk": _candidate_sk(candidate_id),
            },
            UpdateExpression=(
                "SET interviewStatus = :status, startedAt = if_not_exists(startedAt, :startedAt), "
                "updatedAt = :updatedAt"
            ),
            ExpressionAttributeValues={
                ":status": "In Progress",
                ":startedAt": now,
                ":updatedAt": now,
            },
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
        )

    def save_submission(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        answers: list[dict[str, Any]],
        integrity_signals: dict[str, Any],
        submitted_by: str,
        consent_accepted: bool,
    ) -> dict[str, Any]:
        now = _utc_epoch_seconds()
        submission_id = f"{candidate_id}-{now}"
        submission = {
            "pk": _job_candidate_pk(org_id, job_id),
            "sk": _submission_sk(candidate_id, now),
            "entityType": "InterviewSubmission",
            "orgId": org_id,
            "jobId": job_id,
            "candidateId": candidate_id,
            "submissionId": submission_id,
            "answers": answers,
            "integritySignals": _normalize_integrity_signals(integrity_signals),
            "consentAccepted": consent_accepted,
            "submittedBy": submitted_by,
            "submittedAt": now,
            "createdAt": now,
        }
        self.table.put_item(
            Item=submission,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        self.table.update_item(
            Key={
                "pk": _job_candidate_pk(org_id, job_id),
                "sk": _candidate_sk(candidate_id),
            },
            UpdateExpression=(
                "SET interviewStatus = :status, latestSubmissionId = :submissionId, "
                "submittedAt = :submittedAt, updatedAt = :updatedAt "
                "REMOVE candidateSessionToken, candidateSessionExpiresAt"
            ),
            ExpressionAttributeValues={
                ":status": "Interview Submitted",
                ":submissionId": submission_id,
                ":submittedAt": now,
                ":updatedAt": now,
            },
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
        )
        return _public_submission(submission)

    def create_audio_upload_url(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        question_index: int,
        content_type: str,
    ) -> dict[str, Any]:
        if not self.s3_client:
            raise RuntimeError("S3 client is required to create audio upload URLs.")
        if not self.artifact_bucket:
            raise RuntimeError("ARTIFACT_BUCKET environment variable is required.")
        key = _audio_key(org_id, job_id, candidate_id, question_index, content_type)
        upload_url = self.s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.artifact_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )
        return {
            "method": "PUT",
            "url": upload_url,
            "bucket": self.artifact_bucket,
            "key": key,
            "expiresIn": 900,
            "headers": {"Content-Type": content_type},
        }

    def get_audio_bytes(self, *, bucket: str, key: str) -> bytes:
        if not self.s3_client:
            raise RuntimeError("S3 client is required to read audio.")
        response = self.s3_client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def save_transcript(
        self,
        *,
        org_id: str,
        job_id: str,
        candidate_id: str,
        question_index: int,
        audio_s3_bucket: str,
        audio_s3_key: str,
        transcript: str,
    ) -> dict[str, Any]:
        now = _utc_epoch_seconds()
        item = {
            "pk": _job_candidate_pk(org_id, job_id),
            "sk": _transcript_sk(candidate_id, question_index),
            "entityType": "InterviewTranscript",
            "orgId": org_id,
            "jobId": job_id,
            "candidateId": candidate_id,
            "questionIndex": question_index,
            "audioS3Bucket": audio_s3_bucket,
            "audioS3Key": audio_s3_key,
            "transcript": transcript,
            "createdAt": now,
            "updatedAt": now,
        }
        self.table.put_item(Item=item)
        return {
            "candidateId": candidate_id,
            "jobId": job_id,
            "questionIndex": question_index,
            "audioS3Key": audio_s3_key,
            "transcript": transcript,
            "createdAt": now,
        }


def _job_candidate_pk(org_id: str, job_id: str) -> str:
    return f"ORG#{org_id}#JOB#{job_id}"


def _candidate_sk(candidate_id: str) -> str:
    return f"CANDIDATE#{candidate_id}"


def _submission_sk(candidate_id: str, submitted_at: int) -> str:
    return f"SUBMISSION#{candidate_id}#{submitted_at}"


def _transcript_sk(candidate_id: str, question_index: int) -> str:
    return f"TRANSCRIPT#{candidate_id}#{question_index}"


def _utc_epoch_seconds() -> int:
    return int(time.time())


def _normalize_integrity_signals(signals: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(signals, dict):
        signals = {}
    tab_switches = _non_negative_int(signals.get("tabSwitches", signals.get("tab_switches", 0)))
    fullscreen_exits = _non_negative_int(signals.get("fullscreenExits", signals.get("fullscreen_exits", 0)))
    copy_paste_attempts = _non_negative_int(
        signals.get("copyPasteAttempts", signals.get("copy_paste_attempts", 0))
    )
    devtools_attempts = _non_negative_int(signals.get("devtoolsAttempts", signals.get("devtools_attempts", 0)))
    screen_count = max(1, _non_negative_int(signals.get("screenCount", signals.get("screen_count", 1))))
    face_not_detected = _non_negative_int(signals.get("faceNotDetected", signals.get("face_not_detected", 0)))
    multiple_faces = _non_negative_int(signals.get("multipleFaces", signals.get("multiple_faces", 0)))
    risk_score = (
        tab_switches * 2
        + copy_paste_attempts * 5
        + fullscreen_exits * 4
        + devtools_attempts * 8
        + multiple_faces * 6
        + max(0, screen_count - 1) * 3
    )
    return {
        "tabSwitches": tab_switches,
        "fullscreenExits": fullscreen_exits,
        "copyPasteAttempts": copy_paste_attempts,
        "devtoolsAttempts": devtools_attempts,
        "screenCount": screen_count,
        "totalTimeAwaySeconds": _non_negative_float(
            signals.get("totalTimeAwaySeconds", signals.get("total_time_away_seconds", 0))
        ),
        "faceNotDetected": face_not_detected,
        "multipleFaces": multiple_faces,
        "riskScore": risk_score,
        "riskLevel": _risk_level(risk_score),
        "flags": _compact_strings(signals.get("flags", []), limit=20, length=160),
        "events": _compact_events(signals.get("events", [])),
    }


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _non_negative_float(value: Any) -> Decimal:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return Decimal("0")
    return Decimal(str(round(max(parsed, 0.0), 1)))


def _risk_level(score: int) -> str:
    if score >= 40:
        return "Critical"
    if score >= 25:
        return "High"
    if score >= 10:
        return "Medium"
    return "Low"


def _compact_strings(values: Any, *, limit: int, length: int) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value)[:length] for value in values[:limit] if str(value).strip()]


def _compact_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    compacted = []
    for event in events[:100]:
        if not isinstance(event, dict):
            continue
        compacted.append({
            "type": str(event.get("type", ""))[:80],
            "questionIndex": _non_negative_int(event.get("questionIndex", event.get("question_index", 0))),
            "timestamp": str(event.get("timestamp", ""))[:80],
            "detail": str(event.get("detail", ""))[:160],
        })
    return compacted


def _audio_key(org_id: str, job_id: str, candidate_id: str, question_index: int, content_type: str) -> str:
    extension = _audio_extension(content_type)
    safe_candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate_id).strip(".-")
    return f"audio/{org_id}/{job_id}/{safe_candidate}/q-{question_index}-{_utc_epoch_seconds()}.{extension}"


def _audio_extension(content_type: str) -> str:
    normalized = (content_type or "").lower()
    if "mp4" in normalized:
        return "m4a"
    if "mpeg" in normalized or "mp3" in normalized:
        return "mp3"
    if "wav" in normalized:
        return "wav"
    return "webm"


def _public_submission(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "orgId": item["orgId"],
        "jobId": item["jobId"],
        "candidateId": item["candidateId"],
        "submissionId": item["submissionId"],
        "answerCount": len(item.get("answers", [])),
        "integritySignals": item.get("integritySignals", {}),
        "consentAccepted": item.get("consentAccepted", False),
        "submittedAt": item.get("submittedAt"),
        "interviewStatus": "Interview Submitted",
    }
