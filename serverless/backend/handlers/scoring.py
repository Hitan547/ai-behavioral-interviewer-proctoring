"""Recruiter scoring API for starting workflows and reading results."""

from __future__ import annotations

import json
import os
from typing import Any

from repositories.scoring_repository import ScoringRepository
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> ScoringRepository:
    return ScoringRepository.from_environment()


def _get_stepfunctions_client() -> Any:
    try:
        import boto3  # type: ignore
    except ImportError as exc:
        raise RuntimeError("boto3 is required in AWS Lambda runtime.") from exc
    return boto3.client("stepfunctions")


def _path_param(event: dict[str, Any], name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name, "")
    return str(value).strip()


def _required_path(event: dict[str, Any]) -> tuple[str, str]:
    job_id = _path_param(event, "jobId")
    candidate_id = _path_param(event, "candidateId")
    if not job_id:
        raise ValueError("jobId path parameter is required.")
    if not candidate_id:
        raise ValueError("candidateId path parameter is required.")
    return job_id, candidate_id


def _start_scoring(event: dict[str, Any], repository: ScoringRepository) -> dict[str, Any]:
    identity = get_identity(event)
    job_id, candidate_id = _required_path(event)
    workflow_arn = os.environ.get("SCORING_WORKFLOW_ARN", "").strip()
    if not workflow_arn:
        raise RuntimeError("SCORING_WORKFLOW_ARN environment variable is required.")

    candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate was not found for this job.")
    submission = repository.get_latest_submission(identity.org_id, job_id, candidate_id)
    if not submission:
        return error_response(400, "Candidate has no submitted interview answers to score.")

    execution_input = {
        "orgId": identity.org_id,
        "jobId": job_id,
        "candidateId": candidate_id,
        "requestedBy": identity.user_id,
    }
    response = _get_stepfunctions_client().start_execution(
        stateMachineArn=workflow_arn,
        input=json.dumps(execution_input, separators=(",", ":")),
    )
    return json_response(202, {
        "message": "Scoring workflow started.",
        "executionArn": response.get("executionArn"),
        "startDate": str(response.get("startDate", "")),
    })


def _get_result(event: dict[str, Any], repository: ScoringRepository) -> dict[str, Any]:
    identity = get_identity(event)
    job_id, candidate_id = _required_path(event)
    result = repository.get_latest_result(identity.org_id, job_id, candidate_id)
    if not result:
        return error_response(404, "Scoring result was not found for this candidate.")
    download_url = repository.create_report_download_url(result)
    if download_url:
        result = dict(result)
        result["reportDownload"] = {
            "method": "GET",
            "url": download_url,
            "expiresIn": 900,
            "contentType": result.get("reportContentType", "application/pdf"),
        }
    return json_response(200, {"result": result})


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
            return _start_scoring(event, repository)
        if method == "GET":
            return _get_result(event, repository)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except RuntimeError as exc:
        return error_response(500, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")
