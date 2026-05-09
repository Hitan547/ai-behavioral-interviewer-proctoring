"""Resume analysis handler — LLM-powered resume-to-JD matching."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

from repositories.candidates_repository import CandidatesRepository
from repositories.interviews_repository import InterviewsRepository
from services.resume_text import extract_resume_text_from_pdf_bytes
from shared.http import error_response, json_response
from shared.identity import get_identity


def _path_param(event: dict[str, Any], name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name, "")
    return str(value).strip()


def _get_groq_api_keys() -> list[str]:
    keys: list[str] = []
    for env_name in ("GROQ_API_KEY", "GROQ_API_KEY_2"):
        env_key = os.environ.get(env_name, "").strip()
        if env_key and env_key not in keys:
            keys.append(env_key)
    parameter_name = os.environ.get("GROQ_API_KEY_PARAMETER_NAME", "").strip()
    if not parameter_name:
        return keys
    try:
        import boto3  # type: ignore
    except ImportError:
        return keys
    response = boto3.client("ssm").get_parameter(Name=parameter_name, WithDecryption=True)
    ssm_key = str(response.get("Parameter", {}).get("Value", "")).strip()
    if ssm_key and ssm_key not in keys:
        keys.append(ssm_key)
    return keys


def _analyse_resume_with_llm(resume_text: str, jd_text: str, api_key: str) -> dict[str, Any]:
    """Call LLM to score a resume against a JD."""
    prompt = (
        "You are an expert recruiter. Analyze this resume against the job description.\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text[:2000]}\n\n"
        f"=== RESUME ===\n{resume_text[:3000]}\n\n"
        "Return ONLY this JSON (no markdown, no extra text):\n"
        '{"matchScore": <number 1-10>, "matchReason": "<1-2 sentence summary>", '
        '"keyMatches": ["skill1", "skill2"], "keyGaps": ["gap1", "gap2"], '
        '"candidateName": "<extracted full name>", "candidateEmail": "<extracted email or empty string>"}'
    )
    body = json.dumps({
        "model": os.environ.get("QUESTION_GENERATION_MODEL", "llama-3.1-8b-instant"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 500,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "TalentryxAIServerless/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Resume analysis provider request failed.") from exc

    raw = str(data["choices"][0]["message"]["content"])
    # Parse JSON from response (handle markdown wrapping)
    import re
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"matchScore": 5, "matchReason": "Could not parse LLM response", "keyMatches": [], "keyGaps": []}


def _extract_email_from_text(text: str) -> str:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    return match.group(0).strip().lower() if match else ""


def _is_placeholder_email(email: str) -> bool:
    return not email or email.lower().endswith("@pending.local")


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
        identity = get_identity(event)
        job_id = _path_param(event, "jobId")
        if not job_id:
            return error_response(400, "jobId path parameter is required.")

        # Get job and candidates
        table_name = os.environ.get("TABLE_NAME")
        artifact_bucket = os.environ.get("ARTIFACT_BUCKET", "")
        if not table_name:
            raise RuntimeError("TABLE_NAME environment variable is required.")

        import boto3  # type: ignore
        table = boto3.resource("dynamodb").Table(table_name)
        s3_client = boto3.client("s3")

        # Get job
        job_response = table.get_item(Key={"pk": f"ORG#{identity.org_id}", "sk": f"JOB#{job_id}"})
        job = job_response.get("Item")
        if not job:
            return error_response(404, "Job not found.")

        jd_text = str(job.get("jdText", ""))
        if not jd_text:
            return error_response(400, "Job has no description to match against.")
        shortlist_threshold = _float_score(job.get("shortlistThreshold", 7), 7)

        # Get all candidates
        candidates_response = table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"ORG#{identity.org_id}#JOB#{job_id}",
                ":prefix": "CANDIDATE#",
            },
        )
        candidates = candidates_response.get("Items", [])
        if not candidates:
            return error_response(400, "No candidates found for this job. Upload resumes first.")

        api_keys = _get_groq_api_keys()
        results = []

        for candidate in candidates:
            candidate_id = candidate.get("candidateId", "")
            name = candidate.get("name", "Unknown")
            email = candidate.get("email", "")
            resume_key = candidate.get("resumeS3Key", "")

            # Try to read and analyse the resume
            analysis = {"matchScore": 5, "matchReason": "Resume not available", "keyMatches": [], "keyGaps": []}
            if resume_key:
                try:
                    resume_bytes = s3_client.get_object(Bucket=artifact_bucket, Key=resume_key)["Body"].read()
                    resume_text = extract_resume_text_from_pdf_bytes(resume_bytes)

                    if api_keys:
                        last_error: Exception | None = None
                        for api_key in api_keys:
                            try:
                                analysis = _analyse_resume_with_llm(resume_text, jd_text, api_key)
                                last_error = None
                                break
                            except Exception as exc:
                                last_error = exc
                        if last_error:
                            raise last_error
                        # Update candidate name/email from LLM if extracted
                        extracted_name = analysis.get("candidateName", "").strip()
                        extracted_email = (
                            _extract_email_from_text(resume_text)
                            or analysis.get("candidateEmail", "").strip().lower()
                        )
                        if extracted_name and name in ("Unknown", resume_key.split("/")[-1]):
                            name = extracted_name
                        if extracted_email and "@" in extracted_email and _is_placeholder_email(email):
                            email = extracted_email

                        score_float = _float_score(analysis.get("matchScore", 5), 5)
                        analysis["matchScore"] = score_float
                        shortlisted = score_float >= shortlist_threshold
                        current_status = str(candidate.get("interviewStatus", "Resume Upload Pending"))

                        # Update candidate record with match + shortlist data and extracted info.
                        update_expr = (
                            "SET matchScore = :score, matchReason = :reason, "
                            "shortlisted = :shortlisted, shortlistSource = :source, updatedAt = :updatedAt"
                        )
                        expr_values: dict[str, Any] = {
                            ":score": _decimal_score(score_float),
                            ":reason": analysis.get("matchReason", ""),
                            ":shortlisted": shortlisted,
                            ":source": "ai_match",
                            ":updatedAt": _utc_epoch_seconds(),
                        }
                        if current_status in {"Resume Upload Pending", "Resume Analyzed", "Shortlisted"}:
                            update_expr += ", interviewStatus = :interviewStatus"
                            expr_values[":interviewStatus"] = "Shortlisted" if shortlisted else "Resume Analyzed"
                        if shortlisted:
                            update_expr += ", shortlistedAt = :shortlistedAt"
                            expr_values[":shortlistedAt"] = _utc_epoch_seconds()
                        if extracted_name:
                            update_expr += ", #n = :name"
                            expr_values[":name"] = name
                        if extracted_email and "@" in extracted_email:
                            update_expr += ", email = :email"
                            expr_values[":email"] = email

                        expr_names = {"#n": "name"} if extracted_name else {}
                        table.update_item(
                            Key={
                                "pk": f"ORG#{identity.org_id}#JOB#{job_id}",
                                "sk": f"CANDIDATE#{candidate_id}",
                            },
                            UpdateExpression=update_expr,
                            ExpressionAttributeValues=expr_values,
                            **({"ExpressionAttributeNames": expr_names} if expr_names else {}),
                        )
                    else:
                        analysis["matchReason"] = "GROQ_API_KEY not configured — using default score"
                        score_float = _float_score(analysis.get("matchScore", 5), 5)
                        shortlisted = score_float >= shortlist_threshold
                        current_status = str(candidate.get("interviewStatus", "Resume Upload Pending"))
                        update_expr = (
                            "SET matchScore = :score, matchReason = :reason, "
                            "shortlisted = :shortlisted, shortlistSource = :source, updatedAt = :updatedAt"
                        )
                        expr_values: dict[str, Any] = {
                            ":score": _decimal_score(score_float),
                            ":reason": analysis["matchReason"],
                            ":shortlisted": shortlisted,
                            ":source": "default_match",
                            ":updatedAt": _utc_epoch_seconds(),
                        }
                        if current_status in {"Resume Upload Pending", "Resume Analyzed", "Shortlisted"}:
                            update_expr += ", interviewStatus = :interviewStatus"
                            expr_values[":interviewStatus"] = "Shortlisted" if shortlisted else "Resume Analyzed"
                        if shortlisted:
                            update_expr += ", shortlistedAt = :shortlistedAt"
                            expr_values[":shortlistedAt"] = _utc_epoch_seconds()
                        table.update_item(
                            Key={
                                "pk": f"ORG#{identity.org_id}#JOB#{job_id}",
                                "sk": f"CANDIDATE#{candidate_id}",
                            },
                            UpdateExpression=update_expr,
                            ExpressionAttributeValues=expr_values,
                        )
                except Exception as e:
                    analysis["matchReason"] = f"Error reading resume: {e}"

            results.append({
                "candidateId": candidate_id,
                "name": name,
                "email": email,
                "collegeName": candidate.get("collegeName"),
                "department": candidate.get("department"),
                "graduationYear": candidate.get("graduationYear"),
                "matchScore": analysis.get("matchScore", 5),
                "matchReason": analysis.get("matchReason", ""),
                "keyMatches": analysis.get("keyMatches", []),
                "keyGaps": analysis.get("keyGaps", []),
                "shortlisted": _float_score(analysis.get("matchScore", 5), 5) >= shortlist_threshold,
            })

        # Sort by match score descending
        results.sort(key=lambda r: r.get("matchScore", 0), reverse=True)
        return json_response(200, {"results": results})

    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except RuntimeError as exc:
        return error_response(502, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        import traceback
        traceback.print_exc()
        return error_response(500, "Unexpected server error.")


def _float_score(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(10.0, parsed))


def _decimal_score(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _utc_epoch_seconds() -> int:
    import time
    return int(time.time())
