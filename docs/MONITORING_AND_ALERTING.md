# Monitoring and Alerting Plan

## Goal

Detect production failures before recruiters or candidates report them.

## Minimum CloudWatch Alarms

Create alarms for:

- API Gateway 5xx errors.
- API Gateway 4xx spike.
- Lambda errors per function.
- Lambda throttles.
- Lambda duration approaching timeout.
- Step Functions execution failures.
- DynamoDB throttled requests.
- S3 upload failures or access denied patterns.

## Key Dashboards

Recommended dashboard widgets:

- API request count and latency.
- Lambda errors by function.
- Candidate interview submissions per day.
- Scoring workflow success/failure.
- n8n invite send failures from Lambda logs.
- Groq provider failure/fallback count.

## Log Checks

Search CloudWatch logs for:

```text
Failed to send invite
Groq API key is not configured
Audio transcription provider request failed
Unexpected server error
AccessDenied
Task timed out
```

## Operational Runbook

When invites fail:

1. Check `/psysense/dev/N8N_INVITE_WEBHOOK` in SSM.
2. Confirm the webhook URL is active in n8n.
3. Check Lambda logs for HTTP status returned by n8n.
4. Retry one candidate invite.

When scoring fails:

1. Check Step Functions execution.
2. Check scoring worker Lambda logs.
3. Verify `/psysense/dev/GROQ_API_KEY`.
4. Confirm Groq rate limits/provider status.
5. Retry scoring from recruiter dashboard.

When candidate login fails:

1. Confirm candidate has `Invited` status.
2. Confirm invite username/password in recruiter dashboard.
3. Check candidate URL includes `orgId`, `jobId`, and `candidateId`.
4. Check candidate auth Lambda logs.

