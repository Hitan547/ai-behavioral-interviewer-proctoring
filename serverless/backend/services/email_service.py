"""Email service for sending candidate interview invites."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlencode
from typing import Any


def send_interview_invite(
    *,
    candidate_name: str,
    candidate_email: str,
    job_title: str,
    interview_url: str,
    username: str = "",
    password: str = "",
    sender_email: str = "",
) -> dict[str, Any]:
    """Send interview invite through the approved serverless integration path.

    AWS production does not create SES resources. Configure the external
    invite webhook in SSM Parameter Store using N8N_INVITE_WEBHOOK_PARAMETER_NAME.
    """
    webhook_url = _get_invite_webhook_url()
    if not webhook_url and os.environ.get("ENVIRONMENT") == "local":
        print(
            "[local invite mock]",
            json.dumps({
                "candidate_email": candidate_email,
                "interview_url": interview_url,
                "username": username or candidate_email,
                "password": password,
            }),
        )
        return {
            "sent": True,
            "messageId": "local-invite-mock",
            "to": candidate_email,
            "provider": "local",
        }
    if not webhook_url:
        raise RuntimeError(
            "Candidate invite webhook is not configured. Set N8N_INVITE_WEBHOOK in SSM Parameter Store."
        )
    return _send_invite_via_n8n(
        webhook_url=webhook_url,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        job_title=job_title,
        interview_url=interview_url,
        username=username or candidate_email,
        password=password,
    )


def _send_invite_via_n8n(
    *,
    webhook_url: str,
    candidate_name: str,
    candidate_email: str,
    job_title: str,
    interview_url: str,
    username: str,
    password: str,
) -> dict[str, Any]:
    payload = {
        "brand_name": "Talentryx AI",
        "candidate_name": candidate_name,
        "candidate_email": candidate_email,
        "email": candidate_email,
        "to_email": candidate_email,
        "job_title": job_title,
        "interview_url": interview_url,
        "interviewUrl": interview_url,
        "interview_link": interview_url,
        "interviewLink": interview_url,
        "candidate_url": interview_url,
        "url": interview_url,
        "link": interview_url,
        "username": username,
        "password": password,
        "candidate_username": username,
        "candidate_password": password,
        "login_mode": "candidate_credentials",
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TalentryxAIServerless/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return {
                "sent": True,
                "messageId": f"n8n-{response.status}",
                "to": candidate_email,
                "provider": "n8n",
                "response": response_body[:500],
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"n8n invite webhook failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"n8n invite webhook request failed: {exc}") from exc


def _get_invite_webhook_url() -> str:
    webhook_url = os.environ.get("N8N_INVITE_WEBHOOK", "").strip()
    if webhook_url:
        return webhook_url
    parameter_name = os.environ.get("N8N_INVITE_WEBHOOK_PARAMETER_NAME", "").strip()
    if parameter_name:
        try:
            import boto3  # type: ignore
            response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
            value = str(response.get("Parameter", {}).get("Value", "")).strip()
            if value:
                return value
        except Exception:
            pass
    return ""


def build_interview_url(
    *,
    frontend_url: str,
    job_id: str,
    candidate_id: str,
    org_id: str = "",
) -> str:
    """Build the candidate interview URL."""
    base = frontend_url.rstrip("/")
    query = {
        "mode": "candidate",
        "jobId": job_id,
        "candidateId": candidate_id,
    }
    if org_id:
        query["orgId"] = org_id
    return f"{base}/?{urlencode(query)}"
