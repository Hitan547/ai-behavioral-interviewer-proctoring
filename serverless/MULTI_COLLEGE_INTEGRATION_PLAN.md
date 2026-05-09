# PsySense Multi-College Hiring Integration Plan

## Decision

Do not build a full multi-college system immediately unless PsySense is specifically being sold for campus hiring.

For the current SaaS MVP, keep the product focused on:

1. Recruiter signup and login.
2. Job creation.
3. Resume upload and JD matching.
4. Candidate invite.
5. Proctored AI interview.
6. Interview scoring and recruiter report.
7. Final interview-score shortlist based on open positions.

Multi-college support is useful, but it should be added as a small extension to the existing job/candidate model first. A full college management module can come later.

## Why This Matters

If a recruiter hires from one college, the current model works:

- One job.
- Upload resumes.
- Shortlist.
- Invite.
- Interview.
- Rank final candidates.

If a recruiter hires from multiple colleges for the same role, they need to know:

- Which college each candidate belongs to.
- Whether the JD is targeting one college or many colleges.
- Top candidates overall.
- Top candidates per college.
- Final selection based on interview score and open positions.

## Best Product Approach

Use the word "Drive" in the product only when campus hiring becomes important.

For now, a PsySense job can act as the drive:

```text
Job / Hiring Drive
  title: AIML Engineer
  openPositions: 10
  minPassScore: 60
  targetSources: optional college names

Candidates
  name
  email
  collegeName
  resume
  matchScore
  interviewScore
  proctoringRisk
```

This avoids adding unnecessary complexity while still supporting multi-college data.

## AWS Serverless Compatibility

This plan stays within the CEO-approved serverless resources:

- Amplify for frontend hosting.
- Cognito for recruiter and candidate auth.
- API Gateway for APIs.
- Lambda for business logic.
- DynamoDB for jobs, candidates, colleges, and results.
- S3 for resumes, audio, and reports.
- SSM Parameter Store for secrets.
- SQS or Step Functions only for async scoring workflows if needed.
- CloudWatch for logs and monitoring.

No EC2, RDS, VPC, SES, ECS, EKS, OpenSearch, or SageMaker is required.

## Phase 1: Lightweight Multi-College Metadata

Goal: Support multiple colleges without changing the main architecture.

Add optional fields to candidate records:

```json
{
  "collegeName": "ABC Engineering College",
  "collegeLocation": "Bengaluru",
  "graduationYear": "2026",
  "department": "Computer Science",
  "sourceType": "college"
}
```

Add optional fields to job records:

```json
{
  "driveType": "campus",
  "targetCollegeNames": ["ABC Engineering College", "XYZ Institute"],
  "openPositions": 10
}
```

Frontend changes:

- Add college name input during resume upload.
- Add college column in candidate list.
- Add college filter in recruiter dashboard.
- Add grouping in final interview shortlist:
  - Overall top candidates.
  - Top candidates by college.

Backend changes:

- Store college metadata on candidate item.
- Return college metadata in candidate list API.
- Keep final shortlist based on interview score only.

This is low-risk and can be added without a database migration because DynamoDB items can accept optional attributes.

## Phase 2: Campus Drive View

Goal: Make the recruiter workflow feel like a real campus hiring product.

Add a "Drive" label in the UI:

```text
Drive: AIML Engineer Campus Hiring
JD: AIML Engineer
Open Positions: 10
Target Colleges: ABC, XYZ, DEF
```

Dashboard views:

- All candidates.
- Group by college.
- Compare colleges.
- Final interview-score shortlist.
- Export selected candidate table.

Important rule:

Final selected list must use interview score, not resume score.

Resume score is only for deciding whom to invite.

Interview score is for final ranking after candidates complete the interview.

## Phase 3: Full College Entity

Only build this if recruiters repeatedly ask for campus operations.

Add a separate college item:

```json
{
  "pk": "ORG#orgId",
  "sk": "COLLEGE#collegeId",
  "entityType": "College",
  "collegeId": "collegeId",
  "name": "ABC Engineering College",
  "location": "Bengaluru",
  "contactEmail": "placement@college.edu",
  "createdAt": 1770000000
}
```

Candidate item can then store:

```json
{
  "collegeId": "collegeId",
  "collegeName": "ABC Engineering College"
}
```

This gives clean filters and reporting, but it is more work.

## Recommended DynamoDB Model

Current table can remain single-table.

Existing:

```text
ORG#orgId                         JOB#jobId
ORG#orgId#JOB#jobId               CANDIDATE#candidateId
ORG#orgId#JOB#jobId               RESULT#candidateId#timestamp
```

Future optional college entity:

```text
ORG#orgId                         COLLEGE#collegeId
```

No new database is needed.

## Recruiter UI Plan

Candidate table should show:

- Rank.
- Candidate name.
- Email.
- College.
- Job.
- Interview score.
- Assessment status.
- Proctoring risk.
- Full report.

Filters:

- Job.
- College.
- Passed.
- Review Required.
- Below Threshold.
- Risk level.

Final shortlist:

- Show top N candidates where N equals open positions.
- Use only candidates who completed scoring.
- Must be above min pass score.
- Exclude Review Required from auto-selection.
- Exclude Not Recommended.
- Exclude Expired.
- Allow recruiter to manually review and override.

## API Plan

Create candidate:

```http
POST /jobs/{jobId}/candidates
```

Request body addition:

```json
{
  "name": "Student Name",
  "email": "student@email.com",
  "resumeFilename": "resume.pdf",
  "collegeName": "ABC Engineering College",
  "department": "CSE",
  "graduationYear": "2026"
}
```

List candidates:

```http
GET /jobs/{jobId}/candidates
```

Response includes the same optional college fields.

No new endpoint is needed for Phase 1.

## What To Do Now

Recommended next move:

1. Do not build full College CRUD now.
2. Add optional `collegeName`, `department`, and `graduationYear` to candidates.
3. Add college filter and column in recruiter dashboard.
4. Keep final shortlist based on interview score and open positions.
5. Test with one job containing resumes from 2 or 3 colleges.

This gives the recruiter the multi-college benefit without making the SaaS heavy or fragile.

## When To Stop

Stop after Phase 1 if:

- The product is still being tested locally.
- AWS deployment is not fully verified.
- Candidate invite, interview, scoring, and report flow still need testing.
- Recruiters are not yet specifically asking for college-level analytics.

Build Phase 2 or Phase 3 only after the core product is stable and there is clear demand for campus hiring workflows.
