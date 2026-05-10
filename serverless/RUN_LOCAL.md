# Run The Serverless App Locally

This runs the AWS serverless code locally:

- Backend: Flask wrapper around the real Lambda handlers on `http://localhost:3001`
- Frontend: React/Vite app on `http://localhost:5173`
- AWS mocks: local DynamoDB/moto, filesystem S3, environment-backed SSM, console SES, direct Step Functions worker call

## 1. Backend Env

Use the repo-root `.env` as the one normal place for local backend secrets:

```powershell
Copy-Item .\.env.example .\.env
```

Edit `.env` and set:

```env
GROQ_API_KEY=gsk_your_key_here
N8N_INVITE_WEBHOOK=https://your-n8n-instance/webhook/invite
N8N_RESULT_WEBHOOK=https://your-n8n-instance/webhook/result
FRONTEND_URL=http://localhost:5173
```

Use `serverless\.env` only for serverless-local overrides like `LOCAL_PORT`, `TABLE_NAME`, or a temporary test webhook:

```powershell
Copy-Item .\serverless\.env.example .\serverless\.env
```

The local server loads `serverless\.env` first, then fills missing values from the repo-root `.env`. If the same key exists in both files, `serverless\.env` wins. The backend can run without `GROQ_API_KEY`, but question generation, transcription, and scoring will use fallbacks.

## 2. Start Backend

From repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\serverless\start_local_api.ps1
```

Check:

```powershell
Invoke-RestMethod http://localhost:3001/health
```

Expected:

```json
{"mode":"local","status":"ok","table":"psysense-local","n8nInviteConfigured":true}
```

## 3. Frontend Env

Create `serverless\frontend\.env.local`:

```env
VITE_API_BASE_URL=http://localhost:3001
VITE_COGNITO_USER_POOL_ID=
VITE_COGNITO_CLIENT_ID=
```

Frontend env files must only contain `VITE_*` public values. Do not put Groq keys, n8n webhooks, AWS credentials, or Razorpay secrets in frontend env files.

## 4. Start Frontend

```powershell
cd .\serverless\frontend
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://localhost:5173
```

Click **Local Dev Login**. That signs in as a local recruiter without Cognito.

## 5. Smoke Test

1. Open `Jobs`.
2. Create a job and upload one or more PDF resumes.
3. Click `Analyse Resumes`.
4. Review shortlist.
5. Click `Send Invites`.
6. Use the candidate email and password returned/logged by the local backend.
7. Candidate logs in from the Candidate Login tab.
8. Complete the interview.
9. Recruiter clicks `Score`, then `Result`, then `PDF`.

## Notes

- Local data uses DynamoDB Local if available, otherwise moto in-memory.
- If moto is used, data disappears when backend restarts.
- Invite email is mocked unless `N8N_INVITE_WEBHOOK` is set.
- AWS deploy should store the same secret values in SSM Parameter Store and pass only the SSM parameter names to Lambda.
- This local path uses the same backend handler files as AWS SAM deploy.
