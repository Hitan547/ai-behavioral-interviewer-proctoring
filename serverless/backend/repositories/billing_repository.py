"""DynamoDB repository for organization billing and usage summaries."""

from __future__ import annotations

import os
import time
from typing import Any


PLAN_CATALOG: list[dict[str, Any]] = [
    {
        "id": "trial",
        "name": "Trial",
        "priceLabel": "Free pilot",
        "amountPaise": 0,
        "monthlyInterviewLimit": 50,
        "features": [
            "50 interviews per month",
            "Candidate reports",
            "Basic recruiter dashboard",
            "Proctoring signals",
        ],
    },
    {
        "id": "starter",
        "name": "Starter",
        "priceLabel": "INR 8,250/mo",
        "amountPaise": 825000,
        "monthlyInterviewLimit": 100,
        "features": [
            "100 interviews per month",
            "Multi-user recruiter access",
            "PDF candidate reports",
            "Email support",
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "priceLabel": "INR 24,900/mo",
        "amountPaise": 2490000,
        "monthlyInterviewLimit": 500,
        "popular": True,
        "features": [
            "500 interviews per month",
            "Advanced analytics",
            "API and webhook readiness",
            "Priority support",
        ],
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "priceLabel": "Custom",
        "amountPaise": 0,
        "monthlyInterviewLimit": None,
        "features": [
            "Custom interview volume",
            "Dedicated account manager",
            "Security and procurement support",
            "Custom integrations",
        ],
    },
]

_PLAN_BY_ID = {plan["id"]: plan for plan in PLAN_CATALOG}
_COUNTED_STATUSES = {
    "Invited",
    "In Progress",
    "Completed",
    "Interview Submitted",
    "Scored",
    "Passed",
    "Below Threshold",
}


class BillingRepository:
    def __init__(self, table: Any):
        self.table = table

    @classmethod
    def from_environment(cls) -> "BillingRepository":
        table_name = os.environ.get("TABLE_NAME")
        if not table_name:
            raise RuntimeError("TABLE_NAME environment variable is required.")
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError("boto3 is required in AWS Lambda runtime.") from exc
        table = boto3.resource("dynamodb").Table(table_name)
        return cls(table)

    def get_billing_summary(self, org_id: str) -> dict[str, Any]:
        profile = self._get_profile(org_id) or {}
        plan_id = str(profile.get("subscriptionPlan") or profile.get("subscription_plan") or "trial")
        if plan_id not in _PLAN_BY_ID:
            plan_id = "trial"
        plan = _PLAN_BY_ID[plan_id]
        current_month = str(profile.get("currentMonth") or _current_month())
        computed_used = self._interviews_used_for_month(org_id, current_month)
        stored_used = int(profile.get("usedInterviews") or profile.get("used_interviews") or 0)
        used = max(computed_used, stored_used)
        limit = plan.get("monthlyInterviewLimit")
        remaining = None if limit is None else max(0, int(limit) - used)
        usage_percent = 0 if limit in (None, 0) else min(100, round((used / int(limit)) * 100))
        trial_expires_at = int(profile.get("trialExpiresAt") or profile.get("trial_expires_at") or 0)

        return {
            "organization": {
                "orgId": org_id,
                "orgName": profile.get("orgName") or "Organization",
                "ownerEmail": profile.get("ownerEmail") or profile.get("owner_email"),
            },
            "currentPlan": {
                **plan,
                "status": _plan_status(plan_id, trial_expires_at),
                "trialExpiresAt": trial_expires_at or None,
            },
            "usage": {
                "used": used,
                "limit": limit,
                "remaining": remaining,
                "currentMonth": current_month,
                "usagePercent": usage_percent,
            },
            "plans": PLAN_CATALOG,
            "events": self._list_events(org_id),
            "paymentGateway": {
                "provider": "razorpay",
                "configured": _razorpay_configured(),
            },
        }

    def check_invite_quota(self, org_id: str, additional_interviews: int = 1) -> dict[str, Any]:
        """Return whether the organization can reserve more interview seats."""
        additional = max(0, int(additional_interviews))
        summary = self.get_billing_summary(org_id)
        current_plan = summary["currentPlan"]
        usage = summary["usage"]
        plan_name = current_plan["name"]

        if current_plan.get("status") == "Trial expired":
            return {
                "allowed": False,
                "reason": "trial_expired",
                "message": "Trial period expired. Upgrade your plan before sending more interview invites.",
                "billing": summary,
            }

        limit = usage.get("limit")
        if limit is None or additional == 0:
            return {"allowed": True, "reason": "ok", "message": "OK", "billing": summary}

        remaining = int(usage.get("remaining") or 0)
        if remaining < additional:
            return {
                "allowed": False,
                "reason": "quota_exceeded",
                "message": (
                    f"Monthly interview quota reached for {plan_name}. "
                    f"Used {usage['used']}/{limit} interviews for {usage['currentMonth']}. "
                    "Upgrade your plan or wait until the next billing month."
                ),
                "billing": summary,
            }

        return {"allowed": True, "reason": "ok", "message": "OK", "billing": summary}

    def _get_profile(self, org_id: str) -> dict[str, Any] | None:
        response = self.table.get_item(Key={"pk": _org_pk(org_id), "sk": "PROFILE"})
        return response.get("Item")

    def _list_jobs(self, org_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={":pk": _org_pk(org_id), ":prefix": "JOB#"},
        )
        return response.get("Items", [])

    def _list_events(self, org_id: str) -> list[dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={":pk": _org_pk(org_id), ":prefix": "BILLING#"},
            ScanIndexForward=False,
        )
        events = response.get("Items", [])[:25]
        if events:
            return [_public_event(event) for event in events]
        profile = self._get_profile(org_id) or {}
        created_at = int(profile.get("createdAt") or 0)
        if created_at:
            return [{
                "eventId": f"created-{created_at}",
                "eventType": "created",
                "label": "Account created",
                "oldPlan": None,
                "newPlan": profile.get("subscriptionPlan") or "trial",
                "provider": "system",
                "createdAt": created_at,
            }]
        return []

    def _interviews_used_for_month(self, org_id: str, current_month: str) -> int:
        used = 0
        for job in self._list_jobs(org_id):
            job_id = str(job.get("jobId") or "").strip()
            if not job_id:
                continue
            response = self.table.query(
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues={
                    ":pk": f"ORG#{org_id}#JOB#{job_id}",
                    ":prefix": "CANDIDATE#",
                },
            )
            for candidate in response.get("Items", []):
                status = str(candidate.get("interviewStatus") or "")
                if status not in _COUNTED_STATUSES and not candidate.get("startedAt"):
                    continue
                activity_time = int(
                    candidate.get("submittedAt")
                    or candidate.get("latestResultAt")
                    or candidate.get("startedAt")
                    or candidate.get("inviteSentAt")
                    or 0
                )
                if activity_time and _month_from_epoch(activity_time) == current_month:
                    used += 1
            audit_response = self.table.query(
                KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
                ExpressionAttributeValues={
                    ":pk": f"ORG#{org_id}#JOB#{job_id}",
                    ":prefix": "AUDIT#",
                },
            )
            for event in audit_response.get("Items", []):
                if str(event.get("eventType") or "") != "retest_allowed":
                    continue
                created_at = int(event.get("createdAt") or 0)
                if created_at and _month_from_epoch(created_at) == current_month:
                    used += 1
        return used


def _public_event(item: dict[str, Any]) -> dict[str, Any]:
    event_type = str(item.get("eventType") or "event")
    labels = {
        "created": "Account created",
        "upgraded": "Plan upgraded",
        "renewed": "Plan renewed",
        "downgraded": "Plan downgraded",
        "cancelled": "Subscription cancelled",
        "payment_failed": "Payment failed",
    }
    return {
        "eventId": str(item.get("eventId") or item.get("sk") or ""),
        "eventType": event_type,
        "label": labels.get(event_type, event_type.replace("_", " ").title()),
        "oldPlan": item.get("oldPlan"),
        "newPlan": item.get("newPlan"),
        "provider": item.get("provider") or "system",
        "providerEventId": item.get("providerEventId"),
        "createdAt": item.get("createdAt"),
    }


def _org_pk(org_id: str) -> str:
    return f"ORG#{org_id}"


def _current_month() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def _month_from_epoch(epoch_seconds: int) -> str:
    return time.strftime("%Y-%m", time.gmtime(epoch_seconds))


def _plan_status(plan_id: str, trial_expires_at: int) -> str:
    if plan_id != "trial":
        return "Active"
    if trial_expires_at and trial_expires_at < int(time.time()):
        return "Trial expired"
    return "Trial active"


def _razorpay_configured() -> bool:
    if os.environ.get("RAZORPAY_KEY_ID", "").strip():
        return True
    parameter_name = os.environ.get("RAZORPAY_KEY_ID_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return False
    try:
        import boto3  # type: ignore
        response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
    except Exception:
        return False
    return bool(str(response.get("Parameter", {}).get("Value", "")).strip())
