"""Prepare candidate interview questions from S3 resume + DynamoDB metadata."""

from __future__ import annotations

import os
from typing import Any

from repositories.interviews_repository import InterviewsRepository
from services.question_generator import generate_questions_with_keywords
from services.resume_text import extract_resume_text_from_pdf_bytes
from shared.http import error_response, json_response
from shared.identity import get_identity


def _get_repository() -> InterviewsRepository:
    return InterviewsRepository.from_environment()


def _path_param(event: dict[str, Any], name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name, "")
    return str(value).strip()


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
        candidate_id = _path_param(event, "candidateId")
        if not job_id:
            return error_response(400, "jobId path parameter is required.")
        if not candidate_id:
            return error_response(400, "candidateId path parameter is required.")

        repository = _get_repository()
        job = repository.get_job(identity.org_id, job_id)
        if not job:
            return error_response(404, "Job was not found for this organization.")
        candidate = repository.get_candidate(identity.org_id, job_id, candidate_id)
        if not candidate:
            return error_response(404, "Candidate was not found for this job.")

        resume_bytes = repository.get_resume_bytes(candidate)
        resume_text = extract_resume_text_from_pdf_bytes(resume_bytes)
        questions, question_keywords, vocab = generate_questions_with_keywords(
            resume_text,
            jd_text=str(job.get("jdText", "")),
        )
        prepared = repository.save_prepared_questions(
            org_id=identity.org_id,
            job_id=job_id,
            candidate_id=candidate_id,
            questions=questions,
            question_keywords=question_keywords,
            vocab=vocab,
            resume_text=resume_text,
            prepared_by=identity.user_id,
        )
        return json_response(200, {"interview": prepared})
    except PermissionError as exc:
        return error_response(401, str(exc))
    except ValueError as exc:
        return error_response(400, str(exc))
    except RuntimeError as exc:
        return error_response(502, str(exc))
    except Exception:
        if os.getenv("ENVIRONMENT") == "test":
            raise
        return error_response(500, "Unexpected server error.")
