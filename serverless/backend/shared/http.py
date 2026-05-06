"""HTTP response helpers for API Gateway Lambda proxy integrations."""

from __future__ import annotations

import json
from typing import Any


DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


def json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(body, separators=(",", ":")),
    }


def error_response(status_code: int, message: str) -> dict[str, Any]:
    return json_response(status_code, {"error": message})

