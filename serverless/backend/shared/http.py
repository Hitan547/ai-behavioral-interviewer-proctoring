"""HTTP response helpers for API Gateway Lambda proxy integrations."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}


class _DecimalEncoder(json.JSONEncoder):
    """Handle Decimal values returned by DynamoDB."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            # Return int when there's no fractional part, float otherwise
            if o % 1 == 0:
                return int(o)
            return float(o)
        return super().default(o)


def json_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(body, separators=(",", ":"), cls=_DecimalEncoder),
    }


def error_response(status_code: int, message: str) -> dict[str, Any]:
    return json_response(status_code, {"error": message})

