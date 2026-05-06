# PsySense Serverless MVP

This folder contains the AWS serverless implementation path for PsySense.

It is intentionally separate from the current Streamlit/Docker app so the local demo remains stable.

## CEO Cost Guardrail

Do not create:

- VPC
- EC2
- RDS
- OpenSearch
- SageMaker
- ECS/EKS
- NAT Gateway
- Load Balancer
- ElastiCache
- Redshift

## Current Scope

Implemented first vertical slice:

- `POST /jobs`: create a recruiter job posting.
- `GET /jobs`: list recruiter job postings scoped by organization.
- `POST /jobs/{jobId}/candidates`: create candidate metadata and return an S3 presigned resume upload URL.
- `GET /jobs/{jobId}/candidates`: list candidates scoped to one organization and job.
- `POST /jobs/{jobId}/candidates/{candidateId}/prepare-interview`: read uploaded resume from S3, combine it with DynamoDB job/candidate metadata, generate interview questions, and save prepared interview data.
- `GET /jobs/{jobId}/candidates/{candidateId}/interview`: return prepared questions for the candidate interview flow.
- `POST /jobs/{jobId}/candidates/{candidateId}/interview`: store candidate answers, consent confirmation, and lightweight integrity signals.
- `POST /jobs/{jobId}/candidates/{candidateId}/audio-upload-url`: return an S3 presigned URL for one question's audio recording.
- `POST /jobs/{jobId}/candidates/{candidateId}/questions/{questionIndex}/transcribe`: transcribe uploaded question audio and store the transcript.
- `POST /jobs/{jobId}/candidates/{candidateId}/score`: start the Step Functions scoring workflow.
- `GET /jobs/{jobId}/candidates/{candidateId}/result`: return the latest recruiter scoring result with a presigned PDF report download URL when the report has been generated.
- DynamoDB repository layer.
- Step Functions workflow for scoring orchestration.
- S3 presigned PUT URL generation for PDF resumes.
- S3 resume read path for interview preparation.
- S3 PDF report artifact generation after scoring.
- SSM parameter lookup for the Groq API key used by the question generation Lambda.
- `serverless/backend/requirements.txt` packages the PDF text extraction dependency for Lambda builds.
- SAM template using approved serverless services only.

## Local Tests

From repo root:

```bash
python -m pytest tests/test_serverless_jobs.py tests/test_serverless_candidates.py tests/test_serverless_prepare_interview.py tests/test_serverless_candidate_interview.py tests/test_serverless_scoring.py
```

## Template Validation

Before any deployment, generate/validate the template and inspect it for blocked services.

No AWS deployment should happen without CEO approval.
