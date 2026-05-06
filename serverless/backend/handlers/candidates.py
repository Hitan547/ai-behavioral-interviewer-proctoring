"""Candidates API Lambda handler.

Second serverless vertical slice:
- POST /jobs/{jobId}/candidates creates candidate metadata.
- The create response includes a presigned S3 PUT URL for resume upload.
- GET /jobs/{jobId}/candidates lists candidates for that job and organization.
"""

from __future__ import annotations

import json
import os
from typing import Any

from repositories.candidates_repository import CandidatesRepository
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> CandidatesRepository:
    return CandidatesRepository.from_environment()


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        return {}
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


def _create_candidate(event: dict[str, Any], repository: CandidatesRepository) -> dict[str, Any]:
    identity = get_identity(event)
    job_id = _path_param(event, "jobId")
    if not job_id:
        return error_response(400, "jobId path parameter is required.")

    body = _parse_body(event)
    name = str(body.get("name", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    resume_filename = str(body.get("resumeFilename", body.get("resume_filename", "resume.pdf"))).strip()
    resume_content_type = str(
        body.get("resumeContentType", body.get("resume_content_type", "application/pdf"))
    ).strip()

    if not name:
        return error_response(400, "Candidate name is required.")
    if not email or "@" not in email:
        return error_response(400, "Valid candidate email is required.")
    if not resume_filename.lower().endswith(".pdf"):
        return error_response(400, "Resume filename must be a PDF.")
    if resume_content_type not in {"application/pdf", "application/octet-stream"}:
        return error_response(400, "Resume content type must be application/pdf.")

    result = repository.create_candidate(
        org_id=identity.org_id,
        job_id=job_id,
        recruiter_id=identity.user_id,
        name=name,
        email=email,
        resume_filename=resume_filename,
        resume_content_type=resume_content_type,
    )
    return json_response(201, result)


def _list_candidates(event: dict[str, Any], repository: CandidatesRepository) -> dict[str, Any]:
    identity = get_identity(event)
    job_id = _path_param(event, "jobId")
    if not job_id:
        return error_response(400, "jobId path parameter is required.")
    candidates = repository.list_candidates(identity.org_id, job_id)
    return json_response(200, {"candidates": candidates})


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    repository = _get_repository()

    try:
        if method == "POST":
            return _create_candidate(event, repository)
        if method == "GET":
            return _list_candidates(event, repository)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")

