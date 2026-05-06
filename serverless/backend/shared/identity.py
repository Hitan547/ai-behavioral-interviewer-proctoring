"""Identity extraction helpers for Cognito-protected API Gateway events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequestIdentity:
    org_id: str
    user_id: str
    email: str | None = None
    role: str = "recruiter"


def get_identity(event: dict[str, Any]) -> RequestIdentity:
    claims = _claims_from_event(event)
    org_id = (
        claims.get("custom:org_id")
        or claims.get("org_id")
        or claims.get("orgId")
    )
    user_id = claims.get("sub") or claims.get("username") or claims.get("cognito:username")
    email = claims.get("email")
    role = claims.get("custom:role") or claims.get("role") or "recruiter"

    if not org_id:
        raise PermissionError("Authenticated user is missing org_id claim.")
    if not user_id:
        raise PermissionError("Authenticated user is missing user id claim.")

    return RequestIdentity(
        org_id=str(org_id),
        user_id=str(user_id),
        email=str(email) if email else None,
        role=str(role),
    )


def _claims_from_event(event: dict[str, Any]) -> dict[str, Any]:
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})

    jwt_claims = authorizer.get("jwt", {}).get("claims")
    if isinstance(jwt_claims, dict):
        return jwt_claims

    legacy_claims = authorizer.get("claims")
    if isinstance(legacy_claims, dict):
        return legacy_claims

    return {}

