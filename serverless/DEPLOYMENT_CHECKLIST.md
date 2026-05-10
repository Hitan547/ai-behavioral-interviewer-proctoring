# Talentryx AI Serverless Deployment Checklist

This checklist uses your own Groq key, n8n webhook, frontend URL, and recruiter email. Do not send those secrets to CEO/admin.

Public product name is Talentryx AI. Existing AWS resource prefixes intentionally remain `psysense-*` for continuity; see `BRANDING.md`.

## Current Blocker

The previous stack `psysense-dev` reached `ROLLBACK_FAILED` because IAM user `hitan` could not create/delete IAM roles.

That is an AWS permission problem, not a Groq/n8n/frontend value problem.

Admin must clean the failed stack or deploy the stack with a deployment/admin role before you can create a fresh stack with this name.

## Local Prerequisites

Install and verify:

```powershell
sam.cmd --version
aws --version
```

Expected local tooling:

- SAM CLI available as `sam.cmd`
- AWS CLI v2 available as `aws`
- Node/npm available for the React frontend build

The SAM template currently uses Lambda runtime `python3.10`. SAM CLI can build the Lambda package from `serverless/backend/requirements.txt`; do not use the repo's old `venv310` as the deployment runtime.

If `aws --version` fails, install AWS CLI v2 or open a shell where AWS CLI is on `PATH` before running SSM/deploy commands.

## Values You Control

- `GROQ_API_KEY`: stored in SSM as `/psysense/dev/GROQ_API_KEY`
- `N8N_INVITE_WEBHOOK`: stored in SSM as `/psysense/dev/N8N_INVITE_WEBHOOK`
- `N8N_RESULT_WEBHOOK`: optional, stored in SSM as `/psysense/dev/N8N_RESULT_WEBHOOK`
- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`: optional, stored in SSM if billing is enabled
- `FrontendUrl`: the React app URL used in CORS and candidate invite links
- Recruiter Cognito email: created after the Cognito User Pool exists

## Prepare Your SSM Values

From the repo root:

```powershell
cd "C:\Users\Hitan\OneDrive\Documents\GitHub\ai-behavioral-interviewer-proctoring"

powershell -ExecutionPolicy Bypass -File ".\serverless\prepare_aws_values.ps1" `
  -Region us-east-1 `
  -StageName dev `
  -FrontendUrl "http://localhost:5173"
```

Use `http://localhost:5173` while testing locally. After the frontend is hosted, redeploy with the final hosted URL.

If you are enabling optional result webhooks or Razorpay values now, add:

```powershell
-IncludeResultWebhook
-IncludeRazorpay
```

## Validate The Template

```powershell
sam.cmd validate --template-file serverless\template.yaml
```

Expected result: valid SAM template.

If SAM CLI fails with an `AWS SAM\metadata.json` or temp-folder permission error on Windows, run it from a shell with writable app/temp folders, for example:

```powershell
$env:APPDATA = "$PWD\.sam-local-appdata"
$env:TEMP = "$PWD\serverless\_sam_tmp_local"
$env:TMP = $env:TEMP
$env:SAM_CLI_TELEMETRY = "0"
New-Item -ItemType Directory -Force -Path $env:APPDATA, $env:TEMP | Out-Null
sam.cmd validate --template-file serverless\template.yaml --region us-east-1
```

## Build With SAM

Use SAM build so Lambda dependencies from `serverless/backend/requirements.txt` are vendored into the deployment artifact.

```powershell
sam.cmd build `
  --template-file serverless\template.yaml `
  --build-dir serverless\.aws-sam\build
```

Do not replace this with raw `aws cloudformation package`; that skips the Python dependency build step.

This build has been verified locally with SAM CLI. Warnings about SAM telemetry metadata are not deployment blockers if the build ends with `Build Succeeded`.

## Guardrail Scan Before Deploy

Scan the built template:

```powershell
Select-String -Path ".\serverless\.aws-sam\build\template.yaml" `
  -Pattern "AWS::EC2|AWS::RDS|AWS::OpenSearchService|AWS::SageMaker|AWS::ECS|AWS::EKS|ElasticLoadBalancing|ElastiCache|Redshift|NatGateway|LoadBalancer|DBInstance|AWS::SES"
```

Expected result: no output.

## Deploy Backend

For the first deploy, use guided mode:

```powershell
sam.cmd deploy `
  --template-file serverless\.aws-sam\build\template.yaml `
  --stack-name psysense-dev `
  --region us-east-1 `
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND `
  --guided
```

Use these guided values:

- Stack name: `psysense-dev`
- AWS Region: `us-east-1`
- Confirm changes before deploy: `Y`
- Allow SAM CLI IAM role creation: `Y`
- Save arguments to configuration file: `Y`
- StageName: `dev`
- GroqApiKeyParameterName: `/psysense/dev/GROQ_API_KEY`
- N8nInviteWebhookParameterName: `/psysense/dev/N8N_INVITE_WEBHOOK`
- N8nResultWebhookParameterName: `/psysense/dev/N8N_RESULT_WEBHOOK`
- RazorpayKeyIdParameterName: `/psysense/dev/RAZORPAY_KEY_ID`
- RazorpayKeySecretParameterName: `/psysense/dev/RAZORPAY_KEY_SECRET`
- FrontendUrl: `http://localhost:5173` for local testing, or the final hosted frontend URL

For later deploys after `samconfig.toml` exists:

```powershell
sam.cmd build --template-file serverless\template.yaml --build-dir serverless\.aws-sam\build
sam.cmd deploy
```

## After Successful Backend Deploy

Get outputs:

```powershell
aws cloudformation describe-stacks `
  --stack-name psysense-dev `
  --query "Stacks[0].Outputs" `
  --output table `
  --region us-east-1
```

Set frontend env values from the outputs:

```env
VITE_API_BASE_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/dev
VITE_COGNITO_USER_POOL_ID=us-east-1_example
VITE_COGNITO_CLIENT_ID=exampleclientid
```

Create the recruiter Cognito user after `UserPoolId` is available:

```powershell
aws cognito-idp admin-create-user `
  --user-pool-id "USER_POOL_ID_FROM_OUTPUTS" `
  --username "your-recruiter-email@example.com" `
  --user-attributes `
    Name=email,Value=your-recruiter-email@example.com `
    Name=email_verified,Value=true `
    Name="custom:org_id",Value=local-org `
    Name="custom:role",Value=recruiter `
  --temporary-password "ChangeThisTempPassword123!" `
  --region us-east-1
```

Then set a permanent password:

```powershell
aws cognito-idp admin-set-user-password `
  --user-pool-id "USER_POOL_ID_FROM_OUTPUTS" `
  --username "your-recruiter-email@example.com" `
  --password "ChooseYourPermanentPassword123!" `
  --permanent `
  --region us-east-1
```

## Frontend Build

```powershell
cd "C:\Users\Hitan\OneDrive\Documents\GitHub\ai-behavioral-interviewer-proctoring\serverless\frontend"
npm.cmd run build
```

For local testing, keep using Vite with `.env.local`. For hosted testing, deploy `serverless/frontend/dist` to Amplify Hosting or your approved static hosting path, then redeploy the backend with that hosted URL as `FrontendUrl`.

## Smoke Test

After backend and frontend are connected:

1. Sign in as recruiter.
2. Create a job.
3. Add a candidate.
4. Upload a PDF resume.
5. Prepare the interview.
6. Send candidate invite.
7. Open candidate link and submit answers.
8. Start scoring.
9. Confirm a scoring result and PDF report download URL are returned.

Expected deployed behavior:

- Recruiter login uses Cognito.
- Candidate login uses invite credentials created by the app, not the recruiter dashboard.
- Candidate interview, audio upload, transcription, and submit routes are public API routes protected by candidate session validation inside the Lambda handler.
- Recruiter dashboard result routes require Cognito JWT authorization.
- n8n sends candidate invite email through the configured webhook; no SES resource is created.

## CEO/Admin Ask

Ask CEO/admin only for stack cleanup and deploy permission. Do not ask them for your Groq key, n8n webhook, frontend URL, or recruiter email.
