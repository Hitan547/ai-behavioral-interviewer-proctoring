"""Step Functions worker Lambda for scoring interview submissions."""

from __future__ import annotations

from typing import Any

from repositories.scoring_repository import ScoringRepository
from services.report_pdf import generate_report_pdf
from services.scoring_engine import score_interview


def _get_repository() -> ScoringRepository:
    return ScoringRepository.from_environment()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    org_id = str(event.get("orgId", "")).strip()
    job_id = str(event.get("jobId", "")).strip()
    candidate_id = str(event.get("candidateId", "")).strip()
    if not org_id or not job_id or not candidate_id:
        raise ValueError("orgId, jobId, and candidateId are required.")

    repository = _get_repository()
    job = repository.get_job(org_id, job_id)
    candidate = repository.get_candidate(org_id, job_id, candidate_id)
    submission = repository.get_latest_submission(org_id, job_id, candidate_id)
    if not job:
        raise ValueError("Job was not found for this organization.")
    if not candidate:
        raise ValueError("Candidate was not found for this job.")
    if not submission:
        raise ValueError("Candidate has no submitted interview answers.")

    result = score_interview(job=job, candidate=candidate, submission=submission)
    saved = repository.save_scoring_result(
        org_id=org_id,
        job_id=job_id,
        candidate_id=candidate_id,
        submission_id=str(submission.get("submissionId", "")),
        result=result,
    )
    pdf_bytes = generate_report_pdf(
        job=job,
        candidate=candidate,
        submission=submission,
        result=saved,
    )
    saved_with_report = repository.save_report_pdf(
        org_id=org_id,
        job_id=job_id,
        candidate_id=candidate_id,
        result=saved,
        pdf_bytes=pdf_bytes,
    )
    return {"result": saved_with_report}
