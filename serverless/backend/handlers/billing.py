"""Billing API Lambda handler.

This endpoint keeps billing on the approved serverless path:
Cognito + API Gateway + Lambda + DynamoDB. Payment checkout can be layered on
later through Razorpay without adding blocked AWS resources.
"""

from __future__ import annotations

import os
from typing import Any

from repositories.billing_repository import BillingRepository
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> BillingRepository:
    return BillingRepository.from_environment()


def _billing_summary(event: dict[str, Any], repository: BillingRepository) -> dict[str, Any]:
    identity = get_identity(event)
    if identity.role != "recruiter":
        return error_response(403, "Only recruiters can view billing.")
    billing = repository.get_billing_summary(identity.org_id)
    return json_response(200, {"billing": billing})


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
            return _billing_summary(event, repository)
        return error_response(405, f"Method {method or 'UNKNOWN'} is not allowed.")
    except PermissionError as exc:
        return error_response(401, str(exc))
    except RuntimeError as exc:
        return error_response(502, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")
