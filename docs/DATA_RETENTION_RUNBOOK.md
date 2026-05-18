# Data Retention Runbook

## Data Types

Talentryx AI stores:

- Recruiter account and organization metadata.
- Job descriptions.
- Candidate names, emails, college metadata, and resume files.
- Interview answers, transcripts, audio uploads, and proctoring signals.
- Scoring reports and PDF artifacts.
- Billing and usage summaries.

## Recommended MVP Retention

| Data | Suggested Retention |
| --- | --- |
| Job and candidate metadata | Until recruiter deletes job/org |
| Resume files | 90-180 days after drive closes |
| Audio files | 30-90 days after scoring unless customer requires longer |
| Transcripts and reports | 180-365 days for recruiter review |
| Proctoring event counts | Same as interview result |
| Audit/retest events | 365 days |

These are product recommendations, not legal advice. Final retention periods must be approved by the business/legal owner.

## Deletion Workflow

For a candidate deletion request:

1. Locate candidate by org, job, and candidate ID/email.
2. Delete candidate record and related submissions/results from DynamoDB.
3. Delete resume/audio/report objects from S3.
4. Record a minimal deletion audit event if legally allowed.
5. Confirm deletion to the requester.

For a job deletion request:

1. Confirm recruiter authorization.
2. Delete all candidate and interview records under the job.
3. Delete all S3 artifacts under the job prefix.
4. Delete the job item.

## Future Automation

Add a scheduled cleanup Lambda/EventBridge rule to:

- Expire old audio files.
- Expire old resumes after configured retention.
- Keep reports only for the configured customer period.
- Produce cleanup logs for audit.

