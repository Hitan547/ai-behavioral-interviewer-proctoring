"""Recruiter signup for the deployed serverless stack.

Creates a Cognito recruiter user with org/role claims and stores lightweight
organization/recruiter metadata in DynamoDB. This keeps AWS production on the
CEO-approved serverless path: Cognito + Lambda + DynamoDB only.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any

from shared.http import error_response, json_response


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        raise ValueError("Request body must be valid JSON.")
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object.")
    return body


def _safe_org_id(org_name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-") or "org"
    return f"{base[:42]}-{uuid.uuid4().hex[:8]}"


def _validate_password(password: str) -> None:
    if len(password) < 8 or not any(ch.isdigit() for ch in password):
        raise ValueError("Password must be at least 8 characters and include a number.")


def _signup(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event)
    email = str(body.get("email") or body.get("username") or "").strip().lower()
    password = str(body.get("password") or "").strip()
    org_name = str(body.get("orgName") or body.get("org_name") or "").strip()

    if not org_name:
        return error_response(400, "Company/team name is required.")
    if not email or "@" not in email:
        return error_response(400, "Valid recruiter email is required.")
    _validate_password(password)

    user_pool_id = os.environ.get("USER_POOL_ID", "").strip()
    table_name = os.environ.get("TABLE_NAME", "").strip()
    if not user_pool_id:
        raise RuntimeError("USER_POOL_ID environment variable is required.")
    if not table_name:
        raise RuntimeError("TABLE_NAME environment variable is required.")

    import boto3  # type: ignore

    org_id = _safe_org_id(org_name)
    cognito = boto3.client("cognito-idp")
    try:
        cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "custom:org_id", "Value": org_id},
                {"Name": "custom:role", "Value": "recruiter"},
            ],
            MessageAction="SUPPRESS",
        )
        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True,
        )
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code == "UsernameExistsException":
            return error_response(409, "Recruiter already exists. Use Recruiter Login.")
        raise

    now = int(time.time())
    trial_expires_at = now + (14 * 24 * 60 * 60)
    table = boto3.resource("dynamodb").Table(table_name)
    table.put_item(Item={
        "pk": f"ORG#{org_id}",
        "sk": "PROFILE",
        "entityType": "Organization",
        "orgId": org_id,
        "orgName": org_name,
        "ownerEmail": email,
        "subscriptionPlan": "trial",
        "billingStatus": "trialing",
        "maxInterviewsPerMonth": 50,
        "usedInterviews": 0,
        "currentMonth": time.strftime("%Y-%m", time.gmtime(now)),
        "trialStartedAt": now,
        "trialExpiresAt": trial_expires_at,
        "createdAt": now,
        "updatedAt": now,
    })
    table.put_item(Item={
        "pk": f"ORG#{org_id}",
        "sk": f"BILLING#{now}#created",
        "entityType": "BillingEvent",
        "eventId": f"created-{now}",
        "orgId": org_id,
        "eventType": "created",
        "newPlan": "trial",
        "provider": "system",
        "createdAt": now,
    })
    table.put_item(Item={
        "pk": f"ORG#{org_id}",
        "sk": f"RECRUITER#{email}",
        "entityType": "RecruiterProfile",
        "orgId": org_id,
        "email": email,
        "role": "recruiter",
        "createdAt": now,
        "updatedAt": now,
    })

    return json_response(201, {
        "orgId": org_id,
        "orgName": org_name,
        "role": "recruiter",
        "username": email,
        "message": "Recruiter account created. Sign in with these credentials.",
    })


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    try:
        if method == "POST":
            return _signup(event)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except ValueError as exc:
        return error_response(400, str(exc))
    except RuntimeError as exc:
        return error_response(502, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")
