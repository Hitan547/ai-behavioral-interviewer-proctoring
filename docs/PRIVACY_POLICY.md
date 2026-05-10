# PsySense AI - Privacy Policy

Last updated: May 5, 2026

## Overview

PsySense AI is an AI-powered behavioral interview and candidate screening platform. This Privacy Policy explains what information the platform may collect, how it is used, how it is protected, and what choices candidates and recruiters should have.

This document is a pilot-ready draft and should be reviewed by legal counsel before public commercial launch.

## Information We Collect

PsySense may collect the following information:

- Recruiter account details such as name, company name, email address, and organization information.
- Candidate account details such as name, email address, username, and interview assignment.
- Job descriptions and role requirements entered by recruiters.
- Resume files and parsed resume text uploaded for screening.
- Candidate interview answers, transcripts, scores, and generated feedback.
- Audio/video-related interview signals required for interview capture and proctoring.
- Proctoring and integrity signals such as tab switching, fullscreen exits, copy/paste attempts, multiple-face detection, and engagement indicators.
- Usage, billing, subscription, and system activity records.
- Technical logs used for debugging, security, reliability, and abuse prevention.

## How We Use Information

Collected information is used to:

- Create and manage recruiter and candidate accounts.
- Match resumes against job descriptions.
- Generate role-specific interview questions.
- Conduct AI-assisted behavioral interviews.
- Transcribe and evaluate candidate answers.
- Provide structured recruiter dashboards and PDF reports.
- Display proctoring and integrity signals for recruiter review.
- Track usage quotas, subscription status, and billing events.
- Improve platform reliability, security, and user experience.

## AI Evaluation Notice

PsySense provides structured AI-generated insights for recruiter review. Scores, rankings, match results, and proctoring indicators are decision-support signals only.

Final hiring decisions must be made by qualified human reviewers. PsySense should not be used as the sole basis for hiring, rejection, compensation, promotion, or any employment-related decision.

## Proctoring and Integrity Signals

During an interview, PsySense may collect signals that help recruiters understand the interview context. These may include browser tab activity, fullscreen status, copy/paste attempts, multiple-face detection, and engagement indicators.

These signals are not automatic proof of misconduct. They should be reviewed with context by a human recruiter.

## Sharing of Information

Candidate information may be visible to the recruiter or organization that invited the candidate to interview.

PsySense may use third-party service providers for functions such as:

- Speech-to-text and AI model processing.
- Email notifications.
- Payment processing.
- Error monitoring.
- Cloud hosting and database infrastructure.

Information should not be sold to third parties.

## Data Security

PsySense should use reasonable technical and organizational measures to protect data, including:

- Environment-based secret management.
- Password hashing.
- HTTPS in production.
- Database access controls.
- Tenant-aware data access.
- Production monitoring and logging.
- Restricted administrative access.

Before public launch, production deployments should use the CEO-approved serverless AWS architecture, secure environment variables or SSM Parameter Store, and HTTPS.

## Data Retention

Interview, resume, report, and proctoring data should be retained only as long as needed for the recruiting workflow, legal obligations, security, or customer agreement.

Recommended default retention for pilot use:

- Candidate interview data: 90 days after interview completion.
- Resume files and parsed resume text: 90 days after job closure.
- Proctoring events: 90 days after interview completion.
- Account and billing records: retained while the account is active and as legally required.
- Security and system logs: 30 to 90 days unless needed for investigation.

See `docs/DATA_RETENTION_POLICY.md` for the operational retention policy.

## Candidate Rights

Depending on applicable law and customer policy, candidates may request:

- Access to personal data.
- Correction of inaccurate information.
- Deletion of data where legally permitted.
- Explanation of AI-assisted evaluation outputs.
- Information about how their data was used.

Requests should be routed through the recruiter/customer organization or the PsySense administrator.

## Children's Data

PsySense is intended for professional recruiting, education placement, and adult candidate screening contexts. It should not knowingly collect data from children without appropriate consent and legal review.

## Changes to This Policy

This policy may be updated as the product, legal requirements, and deployment model evolve.

## Contact

For privacy questions, contact the organization administering the PsySense deployment or the PsySense product owner.
