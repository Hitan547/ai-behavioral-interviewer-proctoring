"""Candidate credential login for local/demo and lightweight serverless auth."""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any

from shared.http import error_response, json_response


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    if method != "POST":
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")

    try:
        body = json.loads(event.get("body") or "{}")
        username = str(body.get("username") or body.get("email") or "").strip().lower()
        password = str(body.get("password") or "").strip()
        org_id = str(body.get("orgId") or body.get("org_id") or "").strip()
        job_id = str(body.get("jobId") or body.get("job_id") or "").strip()
        candidate_id = str(body.get("candidateId") or body.get("candidate_id") or "").strip()
        if not username or "@" not in username:
            return error_response(400, "Candidate username/email is required.")
        if not password:
            return error_response(400, "Candidate password is required.")

        table_name = os.environ.get("TABLE_NAME")
        if not table_name:
            raise RuntimeError("TABLE_NAME environment variable is required.")

        import boto3  # type: ignore
        table = boto3.resource("dynamodb").Table(table_name)
        items: list[dict[str, Any]] = []
        scan_kwargs: dict[str, Any] = {}
        while True:
            response = table.scan(**scan_kwargs)
            for item in response.get("Items", []):
                if (
                    str(item.get("entityType", "")) == "CandidateProfile"
                    and str(item.get("email", "")).strip().lower() == username
                    and str(item.get("invitePassword", "")).strip() == password
                    and (not org_id or str(item.get("orgId", "")) == org_id)
                    and (not job_id or str(item.get("jobId", "")) == job_id)
                    and (not candidate_id or str(item.get("candidateId", "")) == candidate_id)
                ):
                    items.append(item)
                    break
            if items or "LastEvaluatedKey" not in response:
                break
            scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        if not items:
            return error_response(401, "Candidate credentials are invalid or invite is not active.")

        candidate = items[0]
        if _has_completed_attempt(candidate):
            return error_response(409, "This interview has already been submitted. Contact the recruiter if you need another attempt.")
        session_token = f"cand-{secrets.token_urlsafe(32)}"
        expires_at = int(time.time()) + 60 * 60 * 6
        table.update_item(
            Key={"pk": candidate["pk"], "sk": candidate["sk"]},
            UpdateExpression="SET candidateSessionToken = :token, candidateSessionExpiresAt = :expiresAt",
            ExpressionAttributeValues={
                ":token": session_token,
                ":expiresAt": expires_at,
            },
        )
        return json_response(200, {
            "accessToken": session_token,
            "idToken": session_token,
            "orgId": candidate.get("orgId", org_id),
            "role": "candidate",
            "username": username,
            "jobId": candidate.get("jobId", ""),
            "candidateId": candidate.get("candidateId", ""),
            "candidateName": candidate.get("name", "Candidate"),
        })
    except json.JSONDecodeError:
        return error_response(400, "Request body must be valid JSON.")
    except RuntimeError as exc:
        return error_response(502, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")


def _has_completed_attempt(candidate: dict[str, Any]) -> bool:
    status = str(candidate.get("interviewStatus", ""))
    return bool(candidate.get("latestSubmissionId")) or status in {
        "Interview Submitted",
        "Completed",
        "Scored",
        "Passed",
        "Below Threshold",
        "Review Required",
    }
