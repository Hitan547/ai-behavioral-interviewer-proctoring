"""Candidate interview API Lambda handler."""

from __future__ import annotations

import json
import os
from typing import Any

from repositories.candidate_interviews_repository import CandidateInterviewsRepository
from services.audio_transcription import transcribe_audio_bytes
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> CandidateInterviewsRepository:
    return CandidateInterviewsRepository.from_environment()


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
    identity = get_identity(event)
    job_id, candidate_id = _required_path(event)
    interview = repository.get_prepared_interview(identity.org_id, job_id, candidate_id)
    if not interview:
        return error_response(404, "Candidate interview was not found.")
    return json_response(200, {"interview": interview})


def _submit_interview(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
) -> dict[str, Any]:
    identity = get_identity(event)
    job_id, candidate_id = _required_path(event)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")
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
    return json_response(201, {"submission": submission})


def _create_audio_upload(
    event: dict[str, Any],
    repository: CandidateInterviewsRepository,
) -> dict[str, Any]:
    identity = get_identity(event)
    job_id, candidate_id = _required_path(event)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")

    body = _parse_body(event)
    question_index = _parse_question_index(body.get("questionIndex", body.get("question_index")), len(candidate.get("questions") or []))
    content_type = str(body.get("contentType", body.get("content_type", "audio/webm"))).strip()
    if content_type not in {"audio/webm", "audio/mp4", "audio/mpeg", "audio/wav", "audio/x-wav"}:
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
    identity = get_identity(event)
    job_id, candidate_id = _required_path(event)
    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate interview was not found.")
    questions = candidate.get("questions") or []
    question_index = _parse_question_index(_path_param(event, "questionIndex"), len(questions))

    body = _parse_body(event)
    bucket = str(body.get("audioS3Bucket", body.get("audio_s3_bucket", ""))).strip()
    key = str(body.get("audioS3Key", body.get("audio_s3_key", ""))).strip()
    content_type = str(body.get("contentType", body.get("content_type", "audio/webm"))).strip()
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


def _required_path(event: dict[str, Any]) -> tuple[str, str]:
    job_id = _path_param(event, "jobId")
    candidate_id = _path_param(event, "candidateId")
    if not job_id:
        raise ValueError("jobId path parameter is required.")
    if not candidate_id:
        raise ValueError("candidateId path parameter is required.")
    return job_id, candidate_id


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


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    repository = _get_repository()

    try:
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
