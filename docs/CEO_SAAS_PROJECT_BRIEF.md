# PsySense AI - CEO SaaS Product Brief

## Purpose

This document is a concise, paste-ready project brief for executive review or for asking an external AI evaluator:

> Is this a sellable SaaS product?

The intended answer, based on the current repository and implemented product scope, is:

> Yes. PsySense AI is sellable as an MVP/pilot SaaS product, with a clear path to production SaaS after AWS deployment, payment configuration, security hardening, and legal/privacy readiness.

This brief does not replace technical due diligence. It summarizes what has already been built, why it has commercial value, what remains before launch, and what approval is needed from leadership.

## May 2026 Deployment Update

Leadership has directed that AWS production must use serverless services only. The earlier EC2/RDS/Docker deployment path is now historical/local-demo context only and should not be used for AWS production.

Approved AWS direction:

- Amplify
- Cognito
- API Gateway
- Lambda
- DynamoDB
- S3
- SQS
- Step Functions
- EventBridge
- CloudWatch
- SSM Parameter Store
- Optional Bedrock
- CloudFormation / SAM

Blocked services:

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

Current implementation status:

- The existing Streamlit/Docker app remains the local demo and product-validation environment.
- The new `serverless/` folder contains the approved AWS MVP skeleton and first vertical slice for job creation/listing.
- No AWS resources should be created without approval of the serverless template.

---

## Product Summary

PsySense AI is an AI-powered behavioral interview and candidate screening platform for recruiters, HR teams, staffing agencies, colleges, and companies that need to evaluate candidates at scale.

The platform supports the full workflow from job description to candidate evaluation:

1. Recruiter creates a job posting.
2. Recruiter uploads resumes.
3. AI matches resumes against the job description.
4. The system generates personalized behavioral interview questions.
5. Candidate completes an AI interview.
6. The app captures audio, transcribes answers, and evaluates responses.
7. Proctoring signals are collected during the interview.
8. Recruiter reviews scores, proctoring risk, per-question breakdowns, and PDF reports.

The core value proposition is:

> A lower-cost, transparent, recruiter-controlled alternative to expensive enterprise interview platforms, combining AI scoring, JD-based question generation, resume matching, proctoring, and recruiter analytics.

---

## Why This Is Sellable

PsySense is sellable because it solves a real business problem: recruiters need to screen many candidates quickly without losing structure, consistency, and auditability.

The product is commercially meaningful because it includes:

- A complete recruiter-to-candidate workflow, not only a demo model.
- AI scoring based on behavioral interview dimensions.
- Resume and job description matching.
- JD-specific interview question generation.
- Candidate interview flow with speech-to-text.
- Proctoring and integrity signals.
- Recruiter dashboard and analytics.
- PDF report export.
- Multi-tenant SaaS account structure.
- Subscription plans and usage quotas.
- Production deployment assets for AWS/Docker/PostgreSQL.

This makes it suitable for:

- Early customer pilots.
- HR technology demos.
- College placement screening.
- Staffing agency candidate evaluation.
- SMB hiring teams that cannot afford expensive enterprise platforms.
- Internal enterprise proof-of-concept deployments.

---

## Target Customers

Primary customers:

- Small and mid-sized companies hiring frequently.
- Recruitment agencies and staffing firms.
- Colleges and placement cells.
- Bootcamps and training institutes.
- HR teams needing structured interview screening.

Ideal early adopters:

- Organizations that conduct many first-round interviews.
- Teams that want structured screening before human interviews.
- Recruiters who need faster shortlisting.
- Institutions that need scalable candidate evaluation.

---

## Business Model

The product is designed as a SaaS subscription platform.

Current pricing model:

| Plan | Suggested Price | Usage Limit | Target Customer |
|------|-----------------|-------------|-----------------|
| Trial | Free | Limited interviews | Evaluation and demos |
| Starter | $99/month or India equivalent | 100 interviews/month | Small teams |
| Pro | $299/month or India equivalent | 500 interviews/month | Growing recruiters |
| Enterprise | Custom | Custom limits | Large HR teams/institutions |

Additional monetization options:

- Per-interview overage pricing.
- White-label deployment for colleges or agencies.
- Enterprise private deployment.
- API access for ATS integrations.
- Custom reporting or compliance package.

---

## Implemented Product Modules

### 1. AI Interview Engine

Implemented files:

- `answer_service/main.py`
- `answer_service/llm_engine.py`
- `answer_service/scoring.py`
- `answer_service/prompt.py`
- `audio_capture_robust.py`
- `voice_question.py`

Capabilities:

- Audio capture for candidate answers.
- Speech-to-text using Groq/Whisper integration.
- LLM-based answer evaluation.
- STAR-method behavioral scoring.
- Per-question scoring and reasoning.
- Vocabulary/context support for job-specific questions.

Scoring dimensions:

- Clarity
- Relevance
- STAR structure
- Specificity
- Communication
- Job fit

### 2. Resume and JD Matching

Implemented files:

- `resume_parser.py`
- `matching_service/matcher.py`
- `recruiter_jd_page.py`

Capabilities:

- Recruiter creates a job posting.
- Resume PDFs can be parsed.
- AI evaluates candidate fit against the JD.
- Match score and match reasoning are generated.
- Candidate-specific questions can be generated from JD and resume context.

Commercial value:

- Reduces manual resume screening time.
- Makes candidate interviews more relevant to the role.
- Helps recruiters explain why a candidate was shortlisted.

### 3. Recruiter Dashboard

Implemented files:

- `recruiter_dashboard.py`
- `pdf_export.py`

Capabilities:

- Candidate comparison.
- Interview session review.
- Final score display.
- Cognitive, emotion, and engagement score breakdown.
- Per-question answer review.
- Recruiter notes/verdicts.
- PDF export for candidate reports.
- Proctoring risk visibility.

Commercial value:

- Recruiters get a usable decision-support dashboard.
- Reports can be shared internally.
- Hiring teams can review structured evidence instead of raw interview recordings only.

### 4. Proctoring and Integrity Signals

Implemented files:

- `proctoring.py`
- `proctoring_client.py`
- `engagement_service/main.py`
- `engagement_realtime.py`

Capabilities:

- Tab switch detection.
- Copy/paste blocking and logging.
- Fullscreen enforcement.
- DevTools attempt detection.
- Multi-face detection.
- Engagement/attention tracking.
- Weighted risk scoring.
- Audit trail for recruiter review.

Important positioning:

The system should be presented as collecting integrity signals, not as making final misconduct judgments automatically. Recruiters should remain in the decision loop.

### 5. Multimodal AI Fusion

Implemented files:

- `fusion_service/main.py`
- `fusion_service/fusion_logic.py`
- `emotion_service/main.py`
- `emotion_service/emotion_model.py`
- `insight_service/main.py`
- `insight_service/insight_engine.py`

Capabilities:

- Combines cognitive answer quality, emotion/sentiment, and engagement signals.
- Generates a final candidate score.
- Produces insight summaries for recruiter review.

Commercial value:

- More differentiated than a simple form-based interview tool.
- Gives a structured multi-signal evaluation, while still allowing human review.

### 6. SaaS Authentication and Multi-Tenancy

Implemented files:

- `saas/saas_auth.py`
- `saas/saas_db.py`
- `saas/saas_middleware.py`
- `database.py`

Capabilities:

- Recruiter signup.
- Recruiter login.
- Candidate login.
- Organization creation.
- `org_id` based organization structure.
- Trial plan support.
- API key field support.
- Usage tracking support.
- Tenant-filtered recruiter dashboard paths in key areas.

Commercial value:

- Product is not just a local tool.
- It has the foundation for selling to multiple customer organizations.

### 7. Billing and Usage Limits

Implemented files:

- `saas/saas_billing.py`
- `razorpay_webhooks.py`

Capabilities:

- Subscription plan definitions.
- Trial, Starter, Pro, and Enterprise tiers.
- Monthly interview quotas.
- Billing UI.
- Razorpay order creation.
- Razorpay webhook handling.
- Subscription event logging.

Production note:

Billing must be configured with real payment keys and demo-mode upgrade behavior should be disabled before public launch.

### 8. Production Deployment Assets

Implemented files:

- `Dockerfile`
- `supervisord.conf`
- `deploy/docker-compose.prod.yml`
- `deploy/nginx.conf`
- `.github/workflows/ci.yml`
- `sentry_setup.py`
- `config.py`

Capabilities:

- Dockerized application.
- Multi-service process management.
- PostgreSQL production database support.
- SQLite development support.
- Nginx reverse proxy configuration.
- WebSocket-aware deployment path.
- Sentry monitoring integration.
- CI pipeline for compile/test/lint/build.
- Strict production configuration checks.

Recommended AWS deployment model:

- EC2 for application hosting.
- RDS PostgreSQL for database.
- Docker Compose for initial production pilot.
- Nginx or Application Load Balancer for HTTPS.
- CloudWatch/Sentry for monitoring.
- S3 optional for resume/report storage.

---

## Technical Architecture Summary

Current stack:

- Python 3.10+
- Streamlit frontend
- FastAPI microservices
- SQLAlchemy ORM
- SQLite for local development
- PostgreSQL for production
- Docker
- Supervisord
- Nginx
- Groq API for LLM/STT
- Whisper speech-to-text
- LLaMA-based scoring
- DistilBERT sentiment/emotion analysis
- OpenCV-based engagement signals
- Razorpay billing support
- n8n webhook support for email notifications
- Sentry monitoring support

Architecture style:

- Streamlit application for recruiter and candidate UI.
- FastAPI services for AI scoring, fusion, emotion, insight, and engagement.
- SQLAlchemy shared database layer.
- SaaS module for organization, subscription, and usage tracking.
- Deployment support for containerized production hosting.

---

## Competitive Positioning

Comparable products:

- HireVue
- Spark Hire
- myInterview
- Interviewer.AI
- Modern Hire

PsySense advantages:

- More affordable for SMBs and institutions.
- Transparent scoring dimensions.
- JD-specific question generation.
- Resume-to-JD matching.
- Proctoring signals included.
- Recruiter dashboard included.
- Can be deployed as a managed pilot quickly.

Best positioning:

> PsySense AI is a structured AI interview screening and recruiter analytics platform for high-volume hiring teams.

Avoid positioning it as:

> A fully autonomous hiring decision system.

The safer and more sellable positioning is decision support with human review.

---

## Current Readiness Level

Recommended readiness classification:

> Sellable pilot SaaS / MVP-ready SaaS.

Not yet recommended as:

> Fully public, self-serve SaaS at enterprise compliance level.

Why it is ready for pilot:

- Core product flow exists.
- Recruiter and candidate workflows exist.
- AI scoring exists.
- Proctoring signals exist.
- SaaS account and billing foundation exists.
- Deployment configuration exists.

What remains before broader launch:

- AWS deployment.
- Production PostgreSQL setup.
- Domain and HTTPS.
- Production payment configuration.
- Secret rotation and environment hardening.
- Full tenant isolation audit.
- Legal/privacy pages.
- Candidate consent language.
- End-to-end production testing.

---

## Known Pre-Deployment Checklist

Before CEO approval or AWS deployment, complete or confirm:

- No real secrets committed to Git.
- `.env` stays ignored and local only.
- AWS IAM permissions are available for EC2, RDS, security groups, key pairs, CloudWatch, and optionally S3.
- Production database is RDS PostgreSQL, not SQLite.
- `RECRUITER_DEFAULT_PASSWORD` is strong and not `admin123`.
- `PASSWORD_RESET_SECRET` is changed from the default.
- `APP_BASE_URL` is a public HTTPS URL.
- Groq API keys are configured securely.
- Razorpay or Stripe decision is finalized.
- Billing demo-mode behavior is disabled before public launch.
- n8n production webhooks are configured.
- Sentry DSN is configured for production error tracking.
- Candidate consent and privacy language are approved.
- End-to-end recruiter and candidate flow is tested.

---

## Risk and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| AI scoring may be challenged by candidates | Legal/trust risk | Keep human recruiter in the loop and show transparent score dimensions |
| Proctoring may raise privacy concerns | Trust/compliance risk | Require explicit consent and define data retention |
| Streamlit may feel less polished than custom SaaS UI | Sales/user experience risk | Use for MVP, replace with React/Next.js after validation |
| Billing demo mode may cause unpaid upgrades | Revenue/security risk | Disable demo upgrades in production |
| Tenant isolation must be complete | Data privacy risk | Audit all database queries before public launch |
| AWS permissions are currently insufficient | Deployment blocker | Request correct IAM permissions from leadership |
| Secrets in local files can leak | Security risk | Use AWS Secrets Manager or secure environment variables |

---

## Recommended CEO Ask

Ask for approval for a private production pilot, not a full public launch.

Suggested request:

> I am requesting approval to deploy PsySense AI as a private AWS pilot. The product already includes the core recruiter workflow, AI interview scoring, resume/JD matching, proctoring signals, recruiter analytics, SaaS account structure, usage quotas, billing foundation, and Docker/PostgreSQL deployment support. The goal is to validate it with a small controlled group before public launch.

Required approvals/resources:

- AWS IAM permissions for EC2, RDS, security groups, key pairs, CloudWatch, and optionally S3.
- Budget for one EC2 instance, one RDS PostgreSQL database, domain/HTTPS, API usage, and monitoring.
- Decision on Razorpay vs Stripe billing.
- Approval for privacy policy, candidate consent notice, and data retention policy.
- Permission to run a pilot with 1-3 trusted recruiters or internal HR users.

---

## Suggested Prompt For External ChatGPT Review

Paste the following into ChatGPT or another AI evaluator:

```text
You are reviewing a SaaS product called PsySense AI.

Question: Is this a sellable SaaS product?

Please evaluate based on product completeness, technical implementation, monetization readiness, deployment readiness, market value, and remaining launch risks.

Project summary:

PsySense AI is an AI-powered behavioral interview and candidate screening platform for recruiters, HR teams, staffing agencies, colleges, and companies. It handles job posting creation, resume upload, resume-to-JD matching, AI-generated interview questions, candidate interview flow, speech-to-text transcription, LLM scoring, proctoring signals, recruiter analytics, and PDF reports.

Implemented modules:

1. AI Interview Engine
- Audio capture.
- Groq/Whisper speech-to-text.
- LLaMA-based behavioral answer scoring.
- STAR-method scoring.
- Per-question score breakdown.
- Files: answer_service/, audio_capture_robust.py, voice_question.py.

2. Resume and JD Matching
- Recruiter creates job postings.
- Resume PDFs are parsed.
- AI matches resumes to the job description.
- Candidate-specific questions are generated.
- Files: resume_parser.py, matching_service/, recruiter_jd_page.py.

3. Recruiter Dashboard
- Candidate comparison.
- Interview session review.
- Final score and score breakdowns.
- Recruiter notes and verdicts.
- PDF export.
- Proctoring risk review.
- Files: recruiter_dashboard.py, pdf_export.py.

4. Proctoring and Integrity Signals
- Tab switch detection.
- Copy/paste blocking.
- Fullscreen enforcement.
- DevTools attempt detection.
- Multi-face detection.
- Engagement/attention tracking.
- Weighted proctoring risk score.
- Files: proctoring.py, proctoring_client.py, engagement_service/.

5. Multimodal Fusion
- Combines cognitive answer quality, emotion/sentiment, and engagement signals.
- Produces final candidate score and insights.
- Files: fusion_service/, emotion_service/, insight_service/.

6. SaaS Infrastructure
- Recruiter signup/login.
- Candidate login.
- Organization creation.
- org_id based multi-tenancy foundation.
- Trial plan support.
- Usage quota tracking.
- API key support.
- Files: saas/saas_auth.py, saas/saas_db.py, saas/saas_middleware.py, database.py.

7. Billing
- Trial, Starter, Pro, and Enterprise plans.
- Monthly interview quotas.
- Razorpay order creation and webhooks.
- Billing UI and subscription logs.
- Files: saas/saas_billing.py, razorpay_webhooks.py.

8. Deployment
- Dockerfile.
- Supervisord.
- Docker Compose production stack.
- Nginx config.
- PostgreSQL production support.
- Sentry integration.
- CI pipeline.
- Files: Dockerfile, supervisord.conf, deploy/docker-compose.prod.yml, deploy/nginx.conf, .github/workflows/ci.yml, sentry_setup.py.

Business model:
- Trial: free limited interviews.
- Starter: $99/month or India equivalent.
- Pro: $299/month or India equivalent.
- Enterprise: custom pricing.

Target customers:
- SMB hiring teams.
- Staffing agencies.
- Colleges and placement cells.
- Bootcamps.
- HR teams conducting high-volume first-round interviews.

Recommended positioning:
- Structured AI interview screening and recruiter analytics platform.
- Human-in-the-loop decision support, not fully autonomous hiring decisions.

Remaining pre-launch work:
- AWS deployment using EC2 and RDS PostgreSQL.
- Domain and HTTPS.
- Production payment configuration.
- Secret rotation and production environment hardening.
- Full tenant isolation audit.
- Candidate consent, privacy policy, terms, and data retention policy.
- End-to-end production pilot testing.

Based on this, give a clear verdict: is this sellable as a SaaS product, and if yes, at what readiness level?
```

Expected fair conclusion:

> Yes. PsySense AI is sellable as an MVP/pilot SaaS product. It has a complete enough product workflow, real SaaS foundations, monetization structure, and deployment assets. It should be launched first as a controlled AWS pilot, then hardened for broader self-serve SaaS launch.

---

## Final Executive Verdict

PsySense AI is a sellable SaaS product at MVP/pilot readiness.

The strongest reason is that it is not only an AI demo. It already contains a practical business workflow:

- Recruiter setup.
- Candidate sourcing and matching.
- Interview generation.
- Candidate interview execution.
- AI scoring.
- Proctoring signals.
- Recruiter review.
- Reports.
- SaaS organizations.
- Usage limits.
- Billing foundation.
- Deployment configuration.

The recommended next step is a private AWS pilot, followed by production hardening and customer validation.
