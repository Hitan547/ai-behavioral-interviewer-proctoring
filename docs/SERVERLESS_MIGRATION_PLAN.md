# PsySense AI - Serverless Migration Plan

Last updated: May 5, 2026

## Goal

Move PsySense from the current local/demo architecture to an AWS serverless architecture that follows the CEO-approved service list.

No AWS resources will be created without explicit approval.

## Current State

Current local app:

- Streamlit frontend in `demo_app.py`.
- Recruiter dashboard in `recruiter_dashboard.py`.
- FastAPI microservices for answer scoring, fusion, emotion, insight, and engagement.
- SQLAlchemy data layer using SQLite locally and PostgreSQL-style support.
- Docker Compose and Nginx deployment files.

This stack remains useful for local demos and product validation, but it is not the approved AWS production path.

## Reusable Parts

Reuse the product and business logic:

- Resume parsing and JD/question logic from `resume_parser.py`.
- Scoring prompts and answer evaluation logic from `answer_service/`.
- Fusion logic from `fusion_service/`.
- Insight generation logic from `insight_service/`.
- Proctoring risk concepts from `proctoring.py` and `proctoring_client.py`.
- PDF report content and formatting ideas from `recruiter_dashboard.py` and `pdf_export.py`.
- Trust documents and AI/human-review disclaimer wording from `docs/`.

## Parts To Rebuild

Rebuild for serverless:

- Streamlit UI becomes an Amplify-hosted web frontend.
- FastAPI services become API Gateway + Lambda handlers.
- SQLAlchemy/PostgreSQL models become DynamoDB repository functions.
- Local file storage becomes S3.
- Long-running processing becomes SQS + Step Functions + Lambda.
- `.env` secrets become SSM Parameter Store values.

## Migration Phases

### Phase 1 - Documentation and Guardrails

- Update README to say AWS production is serverless-only.
- Keep Docker/EC2/RDS instructions as local/dev or historical only.
- Add serverless architecture and migration docs.
- Add a serverless skeleton that creates only approved services.

### Phase 2 - First Vertical Slice

Build the smallest deployable flow:

1. Cognito-authenticated recruiter request.
2. `POST /jobs` API.
3. Jobs Lambda validates input.
4. Jobs Lambda saves the job to DynamoDB.
5. `GET /jobs` API lists jobs scoped by `orgId`.

Success criteria:

- No blocked AWS services in template.
- Job data is tenant-scoped.
- Unit tests pass locally.

### Phase 3 - Resume and Questions

- Add S3 presigned upload URL for resumes. **Initial slice implemented.**
- Store candidate metadata in DynamoDB. **Initial slice implemented.**
- Add Lambda wrapper around resume parsing. **Initial slice implemented.**
- Add Lambda wrapper around question generation. **Initial slice implemented.**
- Store generated questions in DynamoDB. **Initial slice implemented.**

### Phase 4 - Candidate Interview

- Add candidate auth or invite-token flow. **Cognito-protected initial API slice implemented; invite-token can replace access later.**
- Show candidate consent notice in frontend. **Backend consent confirmation is enforced in the submission API.**
- Store answers and browser-side integrity signals. **Initial slice implemented.**
- Keep serverless proctoring lightweight:
  - tab switch **implemented in integrity payload**
  - fullscreen exit **implemented in integrity payload**
  - copy/paste attempt **implemented in integrity payload**
  - DevTools key attempt **implemented in integrity payload**
  - optional browser/camera signal later

### Phase 5 - Scoring and Reports

- Use Step Functions to orchestrate scoring. **Initial slice implemented.**
- Score answers with existing scoring logic. **Initial serverless scoring engine implemented.**
- Compute final score and recommendation. **Initial slice implemented.**
- Store results in DynamoDB. **Initial slice implemented.**
- Generate report PDF and save to S3. **Initial slice implemented.**
- Add recruiter dashboard API to read results. **Initial result API implemented.**

### Phase 6 - Pilot Readiness

- Add CloudWatch alarms and log retention.
- Add S3 lifecycle rules.
- Add usage tracking.
- Add internal pilot checklist.
- Add Razorpay live webhook only after core interview flow works.

## Deployment Rules

- Do not create AWS resources until the serverless template is reviewed and approved.
- Do not create VPC, EC2, RDS, OpenSearch, SageMaker, ECS/EKS, NAT Gateway, Load Balancer, ElastiCache, or Redshift.
- Deploy only to a dev/pilot stage first.
- Keep the current Streamlit app local-only unless leadership changes the AWS constraint.

## Definition of Deployment Ready

The serverless version is deployment-ready when:

- The CloudFormation/SAM template validates.
- The template contains no blocked services.
- Unit tests for the first vertical slice pass.
- Cognito authorizer is configured for API Gateway.
- DynamoDB tenant scoping is implemented.
- No secrets are hardcoded.
- SSM parameter names are used for secrets.
- README points to serverless AWS deployment as the approved path.
