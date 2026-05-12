# Production Security Review

## Current Security Posture

Implemented:

- Cognito-backed recruiter authentication.
- Candidate invite credentials.
- Tenant-aware DynamoDB key design.
- SSM Parameter Store for secrets.
- S3 artifact bucket for resumes, audio, and reports.
- Human-in-the-loop decision-support language.
- Candidate consent and proctoring notice pages.
- `.env` and local secrets ignored by Git.

## Immediate Required Actions

- Rotate any AWS access key that was pasted into chat or shared outside AWS.
- Confirm no real secrets are committed:

```powershell
git grep -n "AKIA\\|GROQ_API_KEY\\|N8N_INVITE_WEBHOOK\\|RAZORPAY_KEY_SECRET"
```

- Restrict deploy permissions after frontend deployment is complete.
- Confirm S3 buckets block public access except through CloudFront.
- Confirm CloudFront uses HTTPS.

## Pre-Pilot Checklist

| Area | Check |
| --- | --- |
| Auth | Recruiter login works through Cognito only |
| Candidate access | Candidate can access only their own interview |
| Tenant isolation | One org cannot list another org's jobs/candidates |
| Secrets | Secrets live only in SSM/local ignored `.env` |
| CORS | Backend allows only the real frontend URL |
| S3 | Resume/audio/report objects are not public |
| Logs | Logs do not print passwords, tokens, or full webhook URLs |
| Retest | Retest creates a new attempt and audit context |
| Legal | Candidate consent appears before interview |

## Known Gaps

- No formal penetration test yet.
- No external legal review yet.
- No automated secret scanning gate documented beyond CI hygiene.
- No customer-specific data retention automation yet.
- No enterprise audit export yet.

