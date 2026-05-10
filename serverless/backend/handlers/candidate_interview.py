"""Candidate interview API Lambda handler."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any

from repositories.candidate_interviews_repository import CandidateInterviewsRepository
from services.audio_transcription import transcribe_audio_bytes
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> CandidateInterviewsRepository:
    return CandidateInterviewsRepository.from_environment()


def _get_stepfunctions_client() -> Any:
    try:
        import boto3  # type: ignore
    except ImportError as exc:
        raise RuntimeError("boto3 is required in AWS Lambda runtime.") from exc
    return boto3.client("stepfunctions")


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raise ValueError("Request body must be plain JSON.")
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise ValueError("Request body must be valid JSON.")
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")
    return body


def _path_param(event: dict[str, Any], name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name, "")
    return str(value).strip()


def _get_interview(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
) -> dict[str, Any]:
    job_id, candidate_id = _required_path(event)
    identity = _identity_for_candidate_route(event, repository, job_id, candidate_id)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")
    if _has_completed_attempt(candidate):
        return error_response(409, "This interview has already been submitted.")
    if identity.role == "candidate":
        repository.mark_interview_started(identity.org_id, job_id, candidate_id)
    interview = repository.get_prepared_interview(identity.org_id, job_id, candidate_id)
    if not interview:
        return error_response(404, "Candidate interview was not found.")
    return json_response(200, {"interview": interview})


def _submit_interview(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
) -> dict[str, Any]:
    job_id, candidate_id = _required_path(event)
    identity = _identity_for_candidate_route(event, repository, job_id, candidate_id)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")
    if _has_completed_attempt(candidate):
        return error_response(409, "This interview has already been submitted. Contact the recruiter if you need another attempt.")
    questions = candidate.get("questions") or []
    if not isinstance(questions, list) or not questions:
        return error_response(400, "Interview questions have not been prepared for this candidate.")

    body = _parse_body(event)
    consent_accepted = bool(body.get("consentAccepted", body.get("consent_accepted", False)))
    if not consent_accepted:
        return error_response(400, "Candidate consent must be accepted before submitting answers.")

    answers = _normalize_answers(body.get("answers"), len(questions))
    if not answers:
        return error_response(400, "At least one answer is required.")

    submission = repository.save_submission(
        org_id=identity.org_id,
        job_id=job_id,
        candidate_id=candidate_id,
        answers=answers,
        integrity_signals=body.get("integritySignals", body.get("integrity_signals", {})),
        submitted_by=identity.user_id,
        consent_accepted=consent_accepted,
    )
    scoring = _start_scoring_workflow(identity.org_id, job_id, candidate_id, identity.user_id)
    return json_response(201, {"submission": submission, "scoring": scoring})


def _create_audio_upload(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
) -> dict[str, Any]:
    job_id, candidate_id = _required_path(event)
    identity = _identity_for_candidate_route(event, repository, job_id, candidate_id)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")
    if _has_completed_attempt(candidate):
        return error_response(409, "This interview has already been submitted.")

    body = _parse_body(event)
    question_index = _parse_question_index(body.get("questionIndex", body.get("question_index")), len(candidate.get("questions") or []))
    content_type = _normalize_audio_content_type(body.get("contentType", body.get("content_type", "audio/webm")))
    if not _is_supported_audio_content_type(content_type):
        return error_response(400, "Unsupported audio content type.")
    upload = repository.create_audio_upload_url(
        org_id=identity.org_id,
        job_id=job_id,
        candidate_id=candidate_id,
        question_index=question_index,
        content_type=content_type,
    )
    return json_response(201, {"audioUpload": upload})


def _transcribe_question_audio(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
) -> dict[str, Any]:
    job_id, candidate_id = _required_path(event)
    identity = _identity_for_candidate_route(event, repository, job_id, candidate_id)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")
    if _has_completed_attempt(candidate):
        return error_response(409, "This interview has already been submitted.")
    questions = candidate.get("questions") or []
    question_index = _parse_question_index(_path_param(event, "questionIndex"), len(questions))

    body = _parse_body(event)
    bucket = str(body.get("audioS3Bucket", body.get("audio_s3_bucket", ""))).strip()
    key = str(body.get("audioS3Key", body.get("audio_s3_key", ""))).strip()
    content_type = _normalize_audio_content_type(body.get("contentType", body.get("content_type", "audio/webm")))
    if not bucket or not key:
        return error_response(400, "audioS3Bucket and audioS3Key are required.")
    if not key.startswith(f"audio/{identity.org_id}/{job_id}/{candidate_id}/"):
        return error_response(403, "Audio object does not belong to this candidate.")

    audio_bytes = repository.get_audio_bytes(bucket=bucket, key=key)
    prompt = str(questions[question_index]) if question_index < len(questions) else ""
    transcript = transcribe_audio_bytes(
        audio_bytes,
        filename=key.split("/")[-1],
        content_type=content_type,
        prompt=prompt,
    )
    saved = repository.save_transcript(
        org_id=identity.org_id,
        job_id=job_id,
        candidate_id=candidate_id,
        question_index=question_index,
        audio_s3_bucket=bucket,
        audio_s3_key=key,
        transcript=transcript,
    )
    return json_response(200, {"transcription": saved})


def _transcribe_practice_audio(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event)
    audio_base64 = str(body.get("audioBase64", body.get("audio_base64", ""))).strip()
    filename = str(body.get("filename", "practice-answer.webm")).strip() or "practice-answer.webm"
    content_type = _normalize_audio_content_type(body.get("contentType", body.get("content_type", "audio/webm")))
    prompt = str(body.get("prompt", ""))[:800]

    if not audio_base64:
        return error_response(400, "audioBase64 is required.")
    if not _is_supported_audio_content_type(content_type):
        return error_response(400, "Unsupported audio content type.")

    try:
        audio_bytes = base64.b64decode(audio_base64, validate=True)
    except Exception:
        return error_response(400, "audioBase64 must be valid base64.")

    transcript = transcribe_audio_bytes(
        audio_bytes,
        filename=filename,
        content_type=content_type,
        prompt=prompt,
    )
    return json_response(200, {
        "transcription": {
            "questionIndex": _non_negative_int(body.get("questionIndex", body.get("question_index", 0))),
            "transcript": transcript,
            "contentType": content_type,
        }
    })


def _required_path(event: dict[str, Any]) -> tuple[str, str]:
    job_id = _path_param(event, "jobId")
    candidate_id = _path_param(event, "candidateId")
    if not job_id:
        raise ValueError("jobId path parameter is required.")
    if not candidate_id:
        raise ValueError("candidateId path parameter is required.")
    return job_id, candidate_id


def _normalize_audio_content_type(value: Any) -> str:
    content_type = str(value or "audio/webm").strip().lower()
    return content_type.split(";", 1)[0].strip()


def _is_supported_audio_content_type(content_type: str) -> bool:
    return content_type in {
        "audio/webm",
        "audio/mp4",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
    }


def _identity_for_candidate_route(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
    job_id: str,
    candidate_id: str,
):
    try:
        return get_identity(event)
    except PermissionError:
        token = _bearer_token(event)
        if not token:
            raise
        candidate = repository.find_candidate_by_session_token(
            job_id=job_id,
            candidate_id=candidate_id,
            token=token,
        )
        if not candidate:
            raise PermissionError("Candidate session is invalid or expired.")
        expires_at = int(candidate.get("candidateSessionExpiresAt") or 0)
        if expires_at and expires_at < int(time.time()):
            raise PermissionError("Candidate session has expired.")
        from shared.identity import RequestIdentity
        return RequestIdentity(
            org_id=str(candidate.get("orgId", "")),
            user_id=str(candidate.get("candidateId", candidate_id)),
            email=str(candidate.get("email", "")) or None,
            role="candidate",
        )


def _bearer_token(event: dict[str, Any]) -> str:
    headers = event.get("headers") or {}
    auth_header = ""
    for key, value in headers.items():
        if str(key).lower() == "authorization":
            auth_header = str(value)
            break
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def _normalize_answers(value: Any, question_count: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("answers must be a list.")
    normalized = []
    seen_indexes = set()
    for answer in value:
        if not isinstance(answer, dict):
            raise ValueError("Each answer must be a JSON object.")
        question_index = _parse_question_index(answer.get("questionIndex", answer.get("question_index")), question_count)
        answer_text = str(answer.get("answerText", answer.get("answer_text", ""))).strip()
        if not answer_text:
            raise ValueError("Each answer must include answerText.")
        if question_index in seen_indexes:
            raise ValueError("Each question can only be answered once.")
        seen_indexes.add(question_index)
        normalized.append({
            "questionIndex": question_index,
            "answerText": answer_text[:8000],
            "durationSeconds": _non_negative_int(answer.get("durationSeconds", answer.get("duration_seconds", 0))),
            "audioS3Key": str(answer.get("audioS3Key", answer.get("audio_s3_key", ""))).strip()[:500],
        })
    normalized.sort(key=lambda item: item["questionIndex"])
    return normalized


def _parse_question_index(value: Any, question_count: int) -> int:
    try:
        question_index = int(value)
    except (TypeError, ValueError):
        raise ValueError("Each answer must include a valid questionIndex.")
    if question_index < 0 or question_index >= question_count:
        raise ValueError("questionIndex is outside the prepared question range.")
    return question_index


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _start_scoring_workflow(org_id: str, job_id: str, candidate_id: str, requested_by: str) -> dict[str, Any]:
    workflow_arn = os.environ.get("SCORING_WORKFLOW_ARN", "").strip()
    if not workflow_arn:
        return {"started": False, "reason": "SCORING_WORKFLOW_ARN is not configured."}
    if os.getenv("ENVIRONMENT") == "test" and os.getenv("ENABLE_TEST_SCORING_START") != "1":
        return {"started": False, "reason": "Disabled in unit tests."}

    execution_input = {
        "orgId": org_id,
        "jobId": job_id,
        "candidateId": candidate_id,
        "requestedBy": requested_by,
        "trigger": "candidate_submission",
    }
    try:
        response = _get_stepfunctions_client().start_execution(
            stateMachineArn=workflow_arn,
            input=json.dumps(execution_input, separators=(",", ":")),
        )
        return {
            "started": True,
            "executionArn": response.get("executionArn"),
            "startDate": str(response.get("startDate", "")),
        }
    except Exception as exc:
        return {
            "started": False,
            "reason": f"Scoring workflow could not be started: {exc}",
        }


def _has_completed_attempt(candidate: dict[str, Any]) -> bool:
    status = str(candidate.get("interviewStatus", ""))
    return bool(candidate.get("latestSubmissionId")) or status in {
        "Interview Submitted",
        "Completed",
        "Scored",
        "Passed",
        "Below Threshold",
    }


def _is_practice_transcribe_route(event: dict[str, Any]) -> bool:
    path = (
        event.get("rawPath")
        or event.get("path")
        or event.get("requestContext", {}).get("http", {}).get("path", "")
    )
    return str(path).endswith("/transcribe-practice")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    repository = _get_repository()

    try:
        if method == "POST" and _is_practice_transcribe_route(event):
            return _transcribe_practice_audio(event)
        if method == "GET":
            return _get_interview(event, repository)
        if method == "POST":
            path = (
                event.get("rawPath")
                or event.get("path")
                or event.get("requestContext", {}).get("http", {}).get("path", "")
            )
            if str(path).endswith("/audio-upload-url"):
                return _create_audio_upload(event, repository)
            if "/transcribe" in str(path):
                return _transcribe_question_audio(event, repository)
            return _submit_interview(event, repository)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except RuntimeError as exc:
        return error_response(502, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")
