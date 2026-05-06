# Serverless Frontend and API Integration Plan

This plan explains how to connect a production frontend to the approved PsySense serverless backend.

The current Streamlit app remains useful for local demos. The AWS production frontend should be rebuilt as a browser app hosted on Amplify and connected to API Gateway, Cognito, S3, DynamoDB-backed APIs, Step Functions, and SSM-managed backend secrets.

## Current Reality

The serverless backend MVP already supports:

1. Job creation.
2. Candidate creation.
3. Resume upload through S3 presigned URL.
4. Resume-based question preparation.
5. Candidate question fetch.
6. Candidate answer submission.
7. Lightweight integrity signal submission.
8. Step Functions scoring.
9. Recruiter result fetch.
10. PDF report generation and presigned download.

The frontend is not fully migrated yet.

The current Streamlit interview flow uses:

- `streamlit-webrtc` for camera/audio.
- Server-side audio frame processing.
- Local SQLite/database helpers.
- Local FastAPI services.
- Streamlit session state.
- Local recruiter dashboard data access.

These cannot be treated as production AWS frontend code without rebuilding the browser/API integration.

## Recommended AWS Frontend Target

Use:

- Amplify Hosting for the web app.
- Cognito for recruiter and candidate auth.
- API Gateway for backend calls.
- S3 presigned URLs for resume uploads and report downloads.
- Browser APIs for camera/audio/integrity signal capture.

Recommended frontend stack:

- React + Vite
- TypeScript
- AWS Amplify Auth or Cognito OIDC library
- Plain `fetch` wrapper for API Gateway

Do not use EC2, ECS, Load Balancers, RDS, OpenSearch, or VPC services for the frontend.

## Frontend App Sections

### 1. Recruiter Auth

Purpose:

- Recruiter signs in with Cognito.
- Access token is attached to API Gateway requests.
- Token must include `custom:org_id` and `custom:role`.

Backend dependency:

- Cognito authorizer on API Gateway.

Required frontend state:

- `accessToken`
- `orgId`
- `role`
- `apiBaseUrl`

### 2. Recruiter Dashboard

Required views:

- Jobs list.
- Create job.
- Candidate list per job.
- Create candidate.
- Resume upload status.
- Prepare interview.
- Start scoring.
- Candidate result detail.
- Download PDF report.

API calls:

```text
POST /jobs
GET /jobs
POST /jobs/{jobId}/candidates
GET /jobs/{jobId}/candidates
POST /jobs/{jobId}/candidates/{candidateId}/prepare-interview
POST /jobs/{jobId}/candidates/{candidateId}/score
GET /jobs/{jobId}/candidates/{candidateId}/result
```

Dashboard behavior:

1. Recruiter creates a job with title, JD text, pass score, and optional deadline.
2. Recruiter creates a candidate with name, email, and resume filename.
3. Frontend uploads the resume PDF directly to S3 using returned presigned URL.
4. Recruiter clicks prepare interview.
5. Recruiter sends invite or shares candidate link after invite flow is implemented.
6. Recruiter starts scoring after candidate submits answers.
7. Recruiter opens result and downloads PDF.

### 3. Candidate Interview UI

Required views:

- Candidate sign-in or invite-token entry.
- Consent notice.
- Camera/microphone check.
- Question player.
- Answer recording or typed answer fallback.
- Browser integrity signal capture.
- Submit interview.
- Completion page.

API calls:

```text
GET /jobs/{jobId}/candidates/{candidateId}/interview
POST /jobs/{jobId}/candidates/{candidateId}/interview
```

Submission payload shape:

```json
{
  "consentAccepted": true,
  "answers": [
    {
      "questionIndex": 0,
      "answerText": "Candidate answer text",
      "durationSeconds": 60
    }
  ],
  "integritySignals": {
    "tabSwitches": 0,
    "fullscreenExits": 0,
    "copyPasteAttempts": 0,
    "devtoolsAttempts": 0,
    "events": [
      {
        "type": "tab_switch",
        "questionIndex": 0,
        "timestamp": "2026-05-05T10:00:00Z"
      }
    ]
  }
}
```

## WebRTC, Camera, Audio, and STT Status

The serverless backend currently stores answers and integrity signals. It does not yet provide a production browser audio/video upload and transcription pipeline.

### What Can Work In The First Frontend MVP

- Candidate can read questions.
- Candidate can type answers.
- Browser can capture lightweight integrity events:
  - tab switch
  - fullscreen exit
  - copy/paste attempt
  - DevTools key attempt
- Candidate can submit answers.
- Recruiter can score and view result.

### Audio Recording Slice Status

Initial browser audio recording is implemented in the React frontend:

1. Candidate records per-question audio with `MediaRecorder`.
2. Frontend requests an S3 presigned audio upload URL.
3. Frontend uploads audio directly to S3.
4. Frontend calls the transcription endpoint.
5. Transcript is placed into the answer box for candidate review.

### What Still Needs Additional Work

To match the local Streamlit/WebRTC demo, add these later:

1. Better transcript retry/error UX.
2. Browser-side camera preview.
3. Optional periodic image/frame integrity events.
4. Optional camera presence detection if privacy/consent are updated.

For the lowest-risk serverless MVP, do typed answers first, then add audio recording and transcription as a separate slice.

## Browser Integrity Capture

Frontend should listen for:

```text
visibilitychange
fullscreenchange
copy
paste
keydown for F12, Ctrl+Shift+I, Ctrl+Shift+J, Ctrl+U
```

Suggested event format:

```json
{
  "type": "fullscreen_exit",
  "questionIndex": 2,
  "timestamp": "2026-05-05T10:00:00Z"
}
```

Keep this lightweight for the MVP. Do not add heavy camera proctoring until the core flow is stable.

## API Client Contract

All API requests must include:

```text
Authorization: Bearer <Cognito access token>
Content-Type: application/json
```

Resume upload request must use the presigned S3 URL and headers returned by:

```text
POST /jobs/{jobId}/candidates
```

Report download must use the presigned URL returned by:

```text
GET /jobs/{jobId}/candidates/{candidateId}/result
```

## Migration Phases

### Phase 1 - Recruiter Backend Dashboard MVP

Build recruiter web screens for:

- Sign in.
- Create job.
- List jobs.
- Create candidate.
- Upload resume through S3 presigned URL.
- Prepare interview.
- Start scoring.
- View result.
- Download report.

Success criteria:

- No local database calls.
- All data comes from API Gateway.
- Resume upload goes directly to S3.
- Report download uses presigned S3 URL.

### Phase 2 - Candidate Typed Interview MVP

Build candidate web screens for:

- Sign in or temporary Cognito candidate user.
- Consent.
- Fetch prepared questions.
- Type answers.
- Capture browser integrity signals.
- Submit answers.

Success criteria:

- Candidate submission appears in DynamoDB.
- Scoring workflow can run.
- Recruiter can view result and PDF.

### Phase 3 - Audio Recording and Transcription

Add:

- Browser `MediaRecorder`.
- Presigned S3 upload for audio.
- Lambda transcription.
- Transcript review before submit.

Success criteria:

- Candidate can answer by voice.
- Transcripts are submitted as answers.
- Recruiter result flow remains unchanged.

### Phase 4 - Camera/WebRTC-Like Experience

Add:

- Browser camera preview.
- Fullscreen gate.
- Face-presence integrity signal if implemented client-side.
- Optional snapshot upload only if privacy policy and consent are updated.

Success criteria:

- Camera experience runs fully in browser.
- No EC2 or always-on media server is required.

## Files To Add In A Future Frontend App

Recommended folder:

```text
serverless/frontend/
  package.json
  src/
    main.tsx
    app/App.tsx
    auth/cognito.ts
    api/client.ts
    recruiter/RecruiterDashboard.tsx
    recruiter/JobsView.tsx
    recruiter/CandidateDetail.tsx
    candidate/CandidateInterview.tsx
    candidate/integritySignals.ts
    candidate/mediaRecorder.ts
```

## CEO-Facing Status

Use this wording:

> The AWS serverless backend MVP now covers the main hiring workflow: jobs, candidates, resume upload, question generation, answer submission, scoring, and PDF reports. The next work is frontend migration: building an Amplify-hosted recruiter dashboard and candidate interview UI that calls these APIs. For the first frontend MVP, typed answers and lightweight browser integrity signals are safest. Camera/audio/WebRTC-style recording should be added as a later slice so we do not create costly AWS resources or destabilize deployment.
