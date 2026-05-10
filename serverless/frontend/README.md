# PsySense Serverless Frontend

This folder contains the AWS production frontend scaffold.

Recommended target:

- React + Vite + TypeScript
- Amplify Hosting
- Cognito authentication
- API Gateway requests with Cognito bearer token
- S3 presigned upload/download URLs

Do not move the Streamlit app here directly. The existing Streamlit app uses local database calls, local FastAPI services, and `streamlit-webrtc`, so it remains the local demo path.

## Current Scaffold

Implemented starter screens:

1. Recruiter sign in.
2. Recruiter jobs list/create job.
3. Recruiter candidates list/create candidate.
4. Resume PDF upload using S3 presigned URL.
5. Prepare interview.
6. Candidate typed interview.
7. Submit answers and browser integrity signals.
8. Start scoring.
9. Result detail and PDF report download.

Candidate interview flow now includes:

- Setup by job ID and candidate ID.
- Consent gate.
- Camera/microphone browser permission check.
- Timed question-by-question answer flow.
- Retry/clear current answer.
- Browser audio recording per question.
- S3 audio upload and transcription handoff.
- Review screen before final submit.
- Completion screen after submit.

## Local Commands

PowerShell may block `npm.ps1`, so use `npm.cmd`:

```powershell
Set-Location "serverless\frontend"
npm.cmd install
npm.cmd run dev
npm.cmd run build
```

Create `.env.local` from `.env.example` and set:

```env
VITE_API_BASE_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/dev
VITE_COGNITO_USER_POOL_ID=us-east-1_example
VITE_COGNITO_CLIENT_ID=exampleclientid
```

The app now supports Cognito username/password sign-in. API Gateway requests use the Cognito ID token so the backend receives custom attributes.

The signed-in user's token must include:

- `custom:org_id`
- `custom:role`

The on-page auth panel still lets you edit API/Cognito config during dev so you do not need to rebuild for every stack output change.

## WebRTC And Audio

The first frontend MVP should support typed answers. Browser audio recording, transcription, and camera/WebRTC-style proctoring should be added as later serverless slices.

See `docs/SERVERLESS_FRONTEND_API_INTEGRATION_PLAN.md`.
