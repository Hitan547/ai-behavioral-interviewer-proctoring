"""Jobs API Lambda handler.

First serverless vertical slice:
- POST /jobs creates a job posting scoped to the recruiter's organization.
- GET /jobs lists job postings for that organization.
"""

from __future__ import annotations

import json
import os
from typing import Any

from repositories.jobs_repository import JobsRepository
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> JobsRepository:
    return JobsRepository.from_environment()


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


def _create_job(event: dict[str, Any], repository: JobsRepository) -> dict[str, Any]:
    identity = get_identity(event)
    body = _parse_body(event)
    title = str(body.get("title", "")).strip()
    jd_text = str(body.get("jdText", body.get("jd_text", ""))).strip()
    min_pass_score = body.get("minPassScore", body.get("min_pass_score", 60))
    deadline = body.get("deadline")

    if not title:
        return error_response(400, "Job title is required.")
    if not jd_text:
        return error_response(400, "Job description is required.")

    try:
        min_pass_score = int(min_pass_score)
    except (TypeError, ValueError):
        return error_response(400, "minPassScore must be an integer.")
    if min_pass_score < 0 or min_pass_score > 100:
        return error_response(400, "minPassScore must be between 0 and 100.")

    job = repository.create_job(
        org_id=identity.org_id,
        recruiter_id=identity.user_id,
        title=title,
        jd_text=jd_text,
        min_pass_score=min_pass_score,
        deadline=deadline,
    )
    return json_response(201, {"job": job})


def _list_jobs(event: dict[str, Any], repository: JobsRepository) -> dict[str, Any]:
    identity = get_identity(event)
    jobs = repository.list_jobs(identity.org_id)
    return json_response(200, {"jobs": jobs})


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
            return _create_job(event, repository)
        if method == "GET":
            return _list_jobs(event, repository)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")

