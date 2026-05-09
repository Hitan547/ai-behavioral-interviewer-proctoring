"""Candidates API Lambda handler.

Serverless candidate management:
- POST /jobs/{jobId}/candidates creates candidate metadata.
- GET /jobs/{jobId}/candidates lists candidates for that job and organization.
- PUT /jobs/{jobId}/candidates/{candidateId}/invite sends interview invite email.
"""

from __future__ import annotations

import json
import os
import secrets
import string
from typing import Any

from repositories.billing_repository import BillingRepository
from repositories.candidates_repository import CandidatesRepository
from services.email_service import build_interview_url, send_interview_invite
from shared.http import error_response, json_response
from shared.identity import get_identity


_COMPLETED_ATTEMPT_STATUSES = {
    "Completed",
    "Interview Submitted",
    "Scored",
    "Passed",
    "Below Threshold",
    "Review Required",
}


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
    college_name = str(body.get("collegeName", body.get("college_name", ""))).strip()
    department = str(body.get("department", "")).strip()
    graduation_year = str(body.get("graduationYear", body.get("graduation_year", ""))).strip()
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
        college_name=college_name or None,
        department=department or None,
        graduation_year=graduation_year or None,
    )
    return json_response(201, result)


def _list_candidates(event: dict[str, Any], repository: CandidatesRepository) -> dict[str, Any]:
    identity = get_identity(event)
    job_id = _path_param(event, "jobId")
    if not job_id:
        return error_response(400, "jobId path parameter is required.")
    candidates = repository.list_candidates(identity.org_id, job_id)
    return json_response(200, {"candidates": candidates})


def _update_candidate(event: dict[str, Any], repository: CandidatesRepository) -> dict[str, Any]:
    identity = get_identity(event)
    job_id = _path_param(event, "jobId")
    candidate_id = _path_param(event, "candidateId")
    if not job_id or not candidate_id:
        return error_response(400, "jobId and candidateId path parameters are required.")

    body = _parse_body(event)
    name = body.get("name")
    email = body.get("email")
    college_name = body.get("collegeName", body.get("college_name")) if (
        "collegeName" in body or "college_name" in body
    ) else None
    department = body.get("department") if "department" in body else None
    graduation_year = body.get("graduationYear", body.get("graduation_year")) if (
        "graduationYear" in body or "graduation_year" in body
    ) else None
    shortlisted_value = body.get("shortlisted") if "shortlisted" in body else None

    clean_name = str(name).strip() if name is not None else None
    clean_email = str(email).strip().lower() if email is not None else None
    clean_college_name = str(college_name).strip() if college_name is not None else None
    clean_department = str(department).strip() if department is not None else None
    clean_graduation_year = str(graduation_year).strip() if graduation_year is not None else None
    if clean_name is not None and not clean_name:
        return error_response(400, "Candidate name cannot be empty.")
    if clean_email is not None and (not clean_email or "@" not in clean_email):
        return error_response(400, "Valid candidate email is required.")

    candidate = repository.update_candidate(
        org_id=identity.org_id,
        job_id=job_id,
        candidate_id=candidate_id,
        name=clean_name,
        email=clean_email,
        college_name=clean_college_name,
        department=clean_department,
        graduation_year=clean_graduation_year,
        shortlisted=bool(shortlisted_value) if shortlisted_value is not None else None,
    )
    if not candidate:
        return error_response(404, "Candidate not found.")
    return json_response(200, {"candidate": candidate})


def _send_invite(event: dict[str, Any], repository: CandidatesRepository) -> dict[str, Any]:
    """Send interview invite email to a candidate."""
    identity = get_identity(event)
    job_id = _path_param(event, "jobId")
    candidate_id = _path_param(event, "candidateId")
    if not job_id or not candidate_id:
        return error_response(400, "jobId and candidateId path parameters are required.")

    # Look up job and candidate using DynamoDB keys
    job_resp = repository.table.get_item(
        Key={"pk": f"ORG#{identity.org_id}", "sk": f"JOB#{job_id}"}
    )
    job = job_resp.get("Item")
    if not job:
        return error_response(404, "Job not found.")
    cand_resp = repository.table.get_item(
        Key={"pk": f"ORG#{identity.org_id}#JOB#{job_id}", "sk": f"CANDIDATE#{candidate_id}"}
    )
    candidate = cand_resp.get("Item")
    if not candidate:
        return error_response(404, "Candidate not found.")
    candidate_email = str(candidate.get("email", "")).strip().lower()
    if not candidate_email or candidate_email.endswith("@pending.local"):
        return error_response(
            400,
            "Candidate email was not found in the resume. Add a real email before sending invite.",
        )
    if _has_completed_attempt(candidate):
        return error_response(409, "Interview already has a completed attempt. Use Allow Retest to issue a new attempt.")

    already_reserved = bool(candidate.get("inviteSentAt")) or str(candidate.get("interviewStatus", "")) in {
        "Invited",
        "In Progress",
        "Completed",
        "Interview Submitted",
        "Scored",
        "Passed",
        "Below Threshold",
    }
    quota = BillingRepository(repository.table).check_invite_quota(
        identity.org_id,
        additional_interviews=0 if already_reserved else 1,
    )
    if not quota["allowed"]:
        return json_response(403, {
            "error": quota["message"],
            "reason": quota["reason"],
            "billing": quota["billing"],
        })

    invite_password = str(candidate.get("invitePassword") or "").strip()
    if not invite_password:
        invite_password = _new_invite_password()

    frontend_url = os.environ.get("FRONTEND_URL", "https://talentryx.example.com")
    interview_url = build_interview_url(
        frontend_url=frontend_url,
        job_id=job_id,
        candidate_id=candidate_id,
        org_id=identity.org_id,
    )

    try:
        result = send_interview_invite(
            candidate_name=str(candidate.get("name", "Candidate")),
            candidate_email=candidate_email,
            job_title=str(job.get("title", "Open Position")),
            interview_url=interview_url,
            username=candidate_email,
            password=invite_password,
        )
        now = _utc_epoch_seconds()
        repository.table.update_item(
            Key={"pk": f"ORG#{identity.org_id}#JOB#{job_id}", "sk": f"CANDIDATE#{candidate_id}"},
            UpdateExpression=(
                "SET interviewStatus = :status, inviteUsername = :username, "
                "invitePassword = :password, inviteSentAt = :sentAt, shortlisted = :shortlisted, "
                "shortlistedAt = :shortlistedAt, updatedAt = :updatedAt"
            ),
            ExpressionAttributeValues={
                ":status": "Invited",
                ":username": candidate_email,
                ":password": invite_password,
                ":sentAt": now,
                ":shortlisted": True,
                ":shortlistedAt": now,
                ":updatedAt": now,
            },
        )
        return json_response(200, {
            "message": f"Invite sent to {result['to']}",
            "interviewUrl": interview_url,
            "username": candidate_email,
            "password": invite_password,
            **result,
        })
    except Exception as exc:
        return error_response(500, f"Failed to send invite: {exc}")


def _allow_retest(event: dict[str, Any], repository: CandidatesRepository) -> dict[str, Any]:
    """Issue a fresh candidate invite and keep an audit event for the retest."""
    identity = get_identity(event)
    if identity.role != "recruiter":
        return error_response(403, "Only recruiters can allow a retest.")

    job_id = _path_param(event, "jobId")
    candidate_id = _path_param(event, "candidateId")
    if not job_id or not candidate_id:
        return error_response(400, "jobId and candidateId path parameters are required.")

    job = _get_job(repository, identity.org_id, job_id)
    if not job:
        return error_response(404, "Job not found.")
    candidate = _get_candidate(repository, identity.org_id, job_id, candidate_id)
    if not candidate:
        return error_response(404, "Candidate not found.")
    if not _has_completed_attempt(candidate):
        return error_response(409, "Candidate has not completed an attempt yet. Use Invite for the first attempt.")

    candidate_email = str(candidate.get("email", "")).strip().lower()
    if not candidate_email or candidate_email.endswith("@pending.local"):
        return error_response(400, "Candidate needs a real email before a retest invite can be sent.")

    quota = BillingRepository(repository.table).check_invite_quota(identity.org_id, additional_interviews=1)
    if not quota["allowed"]:
        return json_response(403, {
            "error": quota["message"],
            "reason": quota["reason"],
            "billing": quota["billing"],
        })

    invite_password = _new_invite_password()
    frontend_url = os.environ.get("FRONTEND_URL", "https://talentryx.example.com")
    interview_url = build_interview_url(
        frontend_url=frontend_url,
        job_id=job_id,
        candidate_id=candidate_id,
        org_id=identity.org_id,
    )

    try:
        result = send_interview_invite(
            candidate_name=str(candidate.get("name", "Candidate")),
            candidate_email=candidate_email,
            job_title=str(job.get("title", "Open Position")),
            interview_url=interview_url,
            username=candidate_email,
            password=invite_password,
        )
        now = _utc_epoch_seconds()
        audit_id = f"retest-{candidate_id}-{now}"
        repository.table.update_item(
            Key=_candidate_key(identity.org_id, job_id, candidate_id),
            UpdateExpression=(
                "SET interviewStatus = :status, inviteUsername = :username, "
                "invitePassword = :password, inviteSentAt = :sentAt, shortlisted = :shortlisted, "
                "shortlistedAt = if_not_exists(shortlistedAt, :sentAt), updatedAt = :updatedAt, "
                "lastRetestAt = :sentAt, lastRetestBy = :recruiter, "
                "retestCount = if_not_exists(retestCount, :zero) + :one "
                "REMOVE candidateSessionToken, candidateSessionExpiresAt, startedAt, submittedAt, "
                "latestSubmissionId, latestResultScore, latestRecommendation, latestAssessmentStatus, "
                "latestIntegrityRiskLevel, latestIntegrityRiskScore, latestIntegrityPenalty, "
                "latestResultAt, latestReportGeneratedAt"
            ),
            ExpressionAttributeValues={
                ":status": "Invited",
                ":username": candidate_email,
                ":password": invite_password,
                ":sentAt": now,
                ":shortlisted": True,
                ":updatedAt": now,
                ":recruiter": identity.email or identity.user_id,
                ":zero": 0,
                ":one": 1,
            },
            ConditionExpression="attribute_exists(pk) AND attribute_exists(sk)",
        )
        repository.table.put_item(Item={
            "pk": f"ORG#{identity.org_id}#JOB#{job_id}",
            "sk": f"AUDIT#{candidate_id}#RETEST#{now}",
            "entityType": "CandidateAuditEvent",
            "eventId": audit_id,
            "eventType": "retest_allowed",
            "orgId": identity.org_id,
            "jobId": job_id,
            "candidateId": candidate_id,
            "candidateEmail": candidate_email,
            "candidateName": str(candidate.get("name", "Candidate")),
            "recruiterId": identity.user_id,
            "recruiterEmail": identity.email,
            "previousStatus": candidate.get("interviewStatus"),
            "previousSubmissionId": candidate.get("latestSubmissionId"),
            "previousResultScore": candidate.get("latestResultScore"),
            "createdAt": now,
        })
        return json_response(200, {
            "message": f"Retest invite sent to {result['to']}",
            "interviewUrl": interview_url,
            "username": candidate_email,
            "password": invite_password,
            "auditEventId": audit_id,
            **result,
        })
    except Exception as exc:
        return error_response(500, f"Failed to allow retest: {exc}")


def _get_job(repository: CandidatesRepository, org_id: str, job_id: str) -> dict[str, Any] | None:
    response = repository.table.get_item(Key={"pk": f"ORG#{org_id}", "sk": f"JOB#{job_id}"})
    return response.get("Item")


def _get_candidate(
    repository: CandidatesRepository,
    org_id: str,
    job_id: str,
    candidate_id: str,
) -> dict[str, Any] | None:
    response = repository.table.get_item(Key=_candidate_key(org_id, job_id, candidate_id))
    return response.get("Item")


def _candidate_key(org_id: str, job_id: str, candidate_id: str) -> dict[str, str]:
    return {"pk": f"ORG#{org_id}#JOB#{job_id}", "sk": f"CANDIDATE#{candidate_id}"}


def _has_completed_attempt(candidate: dict[str, Any]) -> bool:
    status = str(candidate.get("interviewStatus", ""))
    return bool(candidate.get("latestSubmissionId")) or status in _COMPLETED_ATTEMPT_STATUSES


def _new_invite_password() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "TX-" + "".join(secrets.choice(alphabet) for _ in range(6))


def _utc_epoch_seconds() -> int:
    import time
    return int(time.time())


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    path = event.get("rawPath", event.get("path", ""))
    repository = _get_repository()

    try:
        if method == "POST" and "/retest" in path:
            return _allow_retest(event, repository)
        if method == "POST":
            return _create_candidate(event, repository)
        if method == "GET":
            return _list_candidates(event, repository)
        if method == "PUT" and "/invite" in path:
            return _send_invite(event, repository)
        if method == "PUT":
            return _update_candidate(event, repository)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")
