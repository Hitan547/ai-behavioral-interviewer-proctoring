"""Recruiter signup for the deployed serverless stack.

Creates a Cognito recruiter user with org/role claims and stores lightweight
organization/recruiter metadata in DynamoDB. This keeps AWS production on the
CEO-approved serverless path: Cognito + Lambda + DynamoDB only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
import uuid
from typing import Any
from urllib.parse import urlparse

from shared.http import error_response, json_response


OTP_TTL_SECONDS = 10 * 60


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


def _get_table():
    table_name = os.environ.get("TABLE_NAME", "").strip()
    if not table_name:
        raise RuntimeError("TABLE_NAME environment variable is required.")

    import boto3  # type: ignore

    return boto3.resource("dynamodb").Table(table_name)


def _get_cognito_client():
    user_pool_id = os.environ.get("USER_POOL_ID", "").strip()
    if not user_pool_id:
        raise RuntimeError("USER_POOL_ID environment variable is required.")

    import boto3  # type: ignore

    return user_pool_id, boto3.client("cognito-idp")


def _hash_otp(email: str, otp: str) -> str:
    secret = os.environ.get("OTP_HASH_SECRET", "") or os.environ.get("USER_POOL_ID", "talentryx-dev")
    return hmac.new(secret.encode("utf-8"), f"{email}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def _otp_key(email: str) -> dict[str, str]:
    return {"pk": f"AUTH#RECRUITER#{email}", "sk": "SIGNUP_OTP"}


def _get_invite_webhook_url() -> str:
    webhook_url = _normalise_webhook_url(os.environ.get("N8N_INVITE_WEBHOOK", ""))
    if webhook_url:
        return webhook_url
    parameter_name = os.environ.get("N8N_INVITE_WEBHOOK_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return ""
    try:
        import boto3  # type: ignore

        response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
        return _normalise_webhook_url(response.get("Parameter", {}).get("Value", ""))
    except Exception:
        return ""


def _normalise_webhook_url(value: Any) -> str:
    webhook_url = str(value or "").strip()
    if not webhook_url or webhook_url.upper() in {"PLACEHOLDER_NOT_SET", "TODO", "CHANGE_ME"}:
        return ""
    parsed = urlparse(webhook_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("n8n webhook URL must be a full https:// URL.")
    return webhook_url


def _post_signup_otp_to_n8n(*, email: str, org_name: str, otp: str) -> None:
    webhook_url = _get_invite_webhook_url()
    if not webhook_url:
        raise RuntimeError("n8n webhook is not configured for recruiter OTP email.")
    payload = {
        "event_type": "recruiter_signup_otp",
        "brand_name": "Talentryx AI",
        "to_email": email,
        "email": email,
        "recruiter_email": email,
        "org_name": org_name,
        "otp": otp,
        "otp_code": otp,
        "expires_in_minutes": OTP_TTL_SECONDS // 60,
        "subject": "Your Talentryx AI signup OTP",
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TalentryxAIServerless/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"n8n OTP webhook failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"n8n OTP webhook request failed: {exc}") from exc


def _request_signup_otp(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event)
    email = str(body.get("email") or body.get("username") or "").strip().lower()
    password = str(body.get("password") or "").strip()
    org_name = str(body.get("orgName") or body.get("org_name") or "").strip()

    if not org_name:
        return error_response(400, "Company/team name is required.")
    if not email or "@" not in email:
        return error_response(400, "Valid recruiter email is required.")
    _validate_password(password)

    user_pool_id, cognito = _get_cognito_client()
    table = _get_table()

    try:
        cognito.admin_get_user(UserPoolId=user_pool_id, Username=email)
        return error_response(409, "Recruiter already exists. Use Recruiter Login.")
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code != "UserNotFoundException":
            raise

    now = int(time.time())
    otp = f"{secrets.randbelow(1_000_000):06d}"
    table.put_item(Item={
        **_otp_key(email),
        "entityType": "RecruiterSignupOtp",
        "email": email,
        "orgName": org_name,
        "passwordHash": hashlib.sha256(password.encode("utf-8")).hexdigest(),
        "otpHash": _hash_otp(email, otp),
        "attempts": 0,
        "expiresAt": now + OTP_TTL_SECONDS,
        "createdAt": now,
        "updatedAt": now,
    })
    _post_signup_otp_to_n8n(email=email, org_name=org_name, otp=otp)
    return json_response(200, {
        "message": "OTP sent to recruiter email.",
        "email": email,
        "expiresInSeconds": OTP_TTL_SECONDS,
    })


def _create_recruiter_account(*, email: str, password: str, org_name: str) -> dict[str, Any]:
    user_pool_id, cognito = _get_cognito_client()
    table = _get_table()

    org_id = _safe_org_id(org_name)
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
    return _create_recruiter_account(email=email, password=password, org_name=org_name)


def _verify_signup_otp(event: dict[str, Any]) -> dict[str, Any]:
    body = _parse_body(event)
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "").strip()
    org_name = str(body.get("orgName") or body.get("org_name") or "").strip()
    otp = re.sub(r"\D+", "", str(body.get("otp") or body.get("code") or ""))

    if not org_name:
        return error_response(400, "Company/team name is required.")
    if not email or "@" not in email:
        return error_response(400, "Valid recruiter email is required.")
    if len(otp) != 6:
        return error_response(400, "Enter the 6-digit OTP sent to your email.")
    _validate_password(password)

    table = _get_table()
    item = table.get_item(Key=_otp_key(email)).get("Item")
    now = int(time.time())
    if not item:
        return error_response(400, "OTP was not requested or has expired.")
    if int(item.get("expiresAt", 0)) < now:
        return error_response(400, "OTP expired. Request a new code.")
    if int(item.get("attempts", 0)) >= 5:
        return error_response(429, "Too many OTP attempts. Request a new code.")
    if item.get("passwordHash") != hashlib.sha256(password.encode("utf-8")).hexdigest():
        return error_response(400, "Signup details changed. Request a new OTP.")
    if str(item.get("orgName", "")) != org_name:
        return error_response(400, "Signup details changed. Request a new OTP.")
    if not hmac.compare_digest(str(item.get("otpHash", "")), _hash_otp(email, otp)):
        table.update_item(
            Key=_otp_key(email),
            UpdateExpression="SET attempts = if_not_exists(attempts, :zero) + :one, updatedAt = :now",
            ExpressionAttributeValues={":zero": 0, ":one": 1, ":now": now},
        )
        return error_response(400, "Invalid OTP.")

    response = _create_recruiter_account(email=email, password=password, org_name=org_name)
    table.delete_item(Key=_otp_key(email))
    return response


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", event.get("httpMethod", ""))
        .upper()
    )
    try:
        if method == "POST":
            path = str(event.get("rawPath") or event.get("path") or "")
            if path.endswith("/request-otp"):
                return _request_signup_otp(event)
            if path.endswith("/verify-otp"):
                return _verify_signup_otp(event)
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
