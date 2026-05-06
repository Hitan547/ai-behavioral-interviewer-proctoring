# PsySense AI - Data Retention Policy

Last updated: May 5, 2026

## Purpose

This policy defines how long PsySense AI data should be retained during pilot and production use.

This is an operational draft and should be reviewed by legal counsel before public commercial launch.

## Retention Principles

PsySense should retain data only as long as necessary for:

- The recruiting workflow.
- Customer support.
- Security and audit needs.
- Billing and account management.
- Legal or contractual obligations.

Data should be deleted or anonymized when it is no longer needed.

## Recommended Default Retention Schedule

| Data Type | Recommended Retention | Notes |
|----------|------------------------|-------|
| Candidate account data | 90 days after related job closure | Longer only if required by customer agreement |
| Resume files | 90 days after job closure | Prefer deletion from storage after retention period |
| Parsed resume text | 90 days after job closure | Delete with resume data |
| Interview transcripts | 90 days after interview completion | Can be exported earlier by recruiter |
| AI scores and reports | 90 days after interview completion | Extend only by customer request |
| Proctoring events | 90 days after interview completion | Treat as sensitive interview context |
| Recruiter accounts | While customer account is active | Delete or deactivate after contract end |
| Organization billing records | As legally required | Follow tax/payment obligations |
| Subscription logs | 1 to 7 years depending on legal need | Confirm jurisdiction before launch |
| Security logs | 30 to 90 days | Keep longer only for incidents |
| Error monitoring logs | 30 to 90 days | Avoid storing secrets or sensitive raw content |

## Pilot Deployment Recommendation

For private pilots, use a simple default:

```text
Delete candidate resumes, interview transcripts, reports, and proctoring data 90 days after the pilot ends unless the customer requests earlier deletion.
```

## Customer-Controlled Retention

For paid customers, retention periods should be configurable or defined in the customer agreement.

Possible customer options:

- 30 days.
- 90 days.
- 180 days.
- Custom enterprise retention.

## Deletion Requests

When a deletion request is approved, delete or anonymize:

- Candidate profile.
- Resume file and parsed text.
- Interview transcript.
- AI scoring records.
- PDF reports.
- Proctoring events.
- Associated exported files where technically possible.

Some records may be retained if legally required, such as billing records or security incident logs.

## Backups

Production backups should follow the same retention intent. If immediate deletion from backups is not technically possible, deleted data should not be restored into active systems except for disaster recovery.

Recommended backup retention:

- Daily database backups for 7 to 30 days during pilot.
- Longer retention only after CEO/customer approval.

## Data Minimization

PsySense should avoid collecting data that is not needed for the interview and recruiter review workflow.

The platform should avoid storing:

- Raw secrets or API keys in logs.
- Unnecessary device identifiers.
- Sensitive personal data unrelated to hiring.
- Long-term raw media unless explicitly required.

## Owner

The product owner or assigned administrator is responsible for enforcing retention policies until an automated retention system is implemented.
