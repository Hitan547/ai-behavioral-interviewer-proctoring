# Talentryx AI — AWS Serverless Deployment Guide

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND                                      │
│                                                                          │
│   S3 (Static Build)  ──►  CloudFront (HTTPS CDN)  ──►  Browser          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            BACKEND                                        │
│                                                                          │
│   API Gateway HTTP API                                                   │
│       │                                                                  │
│       ├── POST /auth/register          → Lambda: Register                │
│       ├── POST /auth/verify-otp        → Lambda: VerifyOTP               │
│       ├── POST /auth/candidate-login   → Lambda: CandidateAuth           │
│       ├── POST /jobs                   → Lambda: Jobs                    │
│       ├── GET  /jobs                   → Lambda: Jobs                    │
│       ├── POST /jobs/{id}/candidates   → Lambda: Candidates              │
│       ├── POST /jobs/{id}/analyse-resumes → Lambda: AnalyseResumes       │
│       ├── POST /jobs/{id}/candidates/{id}/prepare-interview              │
│       │                                → Lambda: PrepareInterview         │
│       ├── GET/POST /jobs/{id}/candidates/{id}/interview                  │
│       │                                → Lambda: CandidateInterview       │
│       ├── POST /jobs/{id}/candidates/{id}/score                          │
│       │                                → Lambda: ScoringApi              │
│       ├── GET  /jobs/{id}/candidates/{id}/result                         │
│       │                                → Lambda: ScoringApi              │
│       └── GET  /billing                → Lambda: Billing                 │
│                                                                          │
│   Step Functions (Scoring Workflow)                                       │
│       └── Lambda: ScoringWorker                                          │
│                                                                          │
│   DynamoDB (single-table: pk/sk)                                         │
│   S3 Artifact Bucket (resumes, audio, reports)                           │
│   SSM Parameter Store (Groq key, n8n webhooks)                           │
│   Secrets Manager (opencrm/frappe-api-key)                               │
│   CloudWatch (logs)                                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                │
│                                                                          │
│   Groq API (LLM + transcription)                                         │
│   n8n Webhook (OTP email + candidate invites + CRM lead creation)        │
│   OpenCRM/Frappe (lead management via API key)                           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Authentication Flow (Company Auth — No Cognito)

Uses the same pattern as `Automated_Unit_Testing/cloud/lambda/register.py`:

```
1. Recruiter enters name, email, mobile → POST /auth/register
2. Lambda calls n8n webhook with OTP + Frappe CRM lead creation
   (uses secret: arn:aws:secretsmanager:us-east-1:976193236457:secret:opencrm/frappe-api-key-iQgSaZ)
3. n8n sends OTP to recruiter's email
4. Recruiter enters OTP → POST /auth/verify-otp
5. Lambda verifies OTP against DynamoDB, returns session token
6. All subsequent API calls use session token in Authorization header

Candidate auth remains credential-based (invite password from recruiter).
```

---

## Prerequisites

- AWS CLI v2 configured (`aws --version`)
- AWS SAM CLI installed (`sam --version`)
- Node.js 18+ and npm (`node --version`)
- Python 3.10 (for `sam build`)
- IAM permissions: Lambda, API Gateway, DynamoDB, S3, Step Functions, SSM, CloudWatch, CloudFormation, IAM roles, Secrets Manager read

---

## Backend Deployment

### Step 1 — Store Secrets in SSM Parameter Store

```bash
# Groq API key (for LLM scoring + transcription)
aws ssm put-parameter \
  --name /psysense/dev/GROQ_API_KEY \
  --value "<your-groq-api-key>" \
  --type SecureString \
  --region us-east-1

# n8n invite webhook (sends candidate interview credentials)
aws ssm put-parameter \
  --name /psysense/dev/N8N_INVITE_WEBHOOK \
  --value "https://n8n.digitransolutions.in/webhook/<your-invite-webhook-id>" \
  --type SecureString \
  --region us-east-1

# n8n result webhook (optional — sends scoring results)
aws ssm put-parameter \
  --name /psysense/dev/N8N_RESULT_WEBHOOK \
  --value "https://n8n.digitransolutions.in/webhook/<your-result-webhook-id>" \
  --type SecureString \
  --region us-east-1
```

The Frappe API key is already stored in Secrets Manager:
```
ARN:  arn:aws:secretsmanager:us-east-1:976193236457:secret:opencrm/frappe-api-key-iQgSaZ
Name: opencrm/frappe-api-key
```

### Step 2 — Validate the SAM Template

```bash
cd /mnt/d/shared/trial/ai-behavioral-interviewer-proctoring/serverless
sam validate --template-file template.yaml --region us-east-1
```

### Step 3 — Build

```bash
sam build
```

If Python 3.10 is not available locally, use Docker:

```bash
sam build --use-container
```

### Step 4 — Deploy Backend Stack

First deployment (guided):

```bash
sam deploy \
  --stack-name talentryx-dev \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --guided
```

Guided parameter values:

| Parameter | Value |
|---|---|
| StageName | `dev` |
| GroqApiKeyParameterName | `/psysense/dev/GROQ_API_KEY` |
| N8nInviteWebhookParameterName | `/psysense/dev/N8N_INVITE_WEBHOOK` |
| N8nResultWebhookParameterName | `/psysense/dev/N8N_RESULT_WEBHOOK` |
| RazorpayKeyIdParameterName | `/psysense/dev/RAZORPAY_KEY_ID` |
| RazorpayKeySecretParameterName | `/psysense/dev/RAZORPAY_KEY_SECRET` |
| FrontendUrl | `http://localhost:5173` (change to CloudFront URL after frontend deploy) |

Subsequent deployments (after `samconfig.toml` is saved):

```bash
sam build
sam deploy --no-confirm-changeset
```

### Step 5 — Get Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name talentryx-dev \
  --query "Stacks[0].Outputs" \
  --output table \
  --region us-east-1
```

Note these values:
- `ApiEndpoint` — backend API URL
- `TableName` — DynamoDB table name
- `ArtifactBucketName` — S3 bucket for resumes/audio/reports

---

## Frontend Deployment

### Step 1 — Configure Frontend Environment

Create `serverless/frontend/.env.production`:

```env
VITE_API_BASE_URL=<ApiEndpoint from stack outputs>
VITE_LOCAL_DEV=false
```

### Step 2 — Build Frontend

```bash
cd /mnt/d/shared/trial/ai-behavioral-interviewer-proctoring/serverless/frontend
npm install
npm run build
```

Output goes to `serverless/frontend/dist/`.

### Step 3 — Create S3 Bucket for Frontend

```bash
aws s3 mb s3://talentryx-frontend-976193236457 --region us-east-1

# Block public access (CloudFront will serve it)
aws s3api put-public-access-block \
  --bucket talentryx-frontend-976193236457 \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

### Step 4 — Upload Build to S3

```bash
aws s3 sync serverless/frontend/dist/ s3://talentryx-frontend-976193236457/ --delete
```

### Step 5 — Create CloudFront Distribution

```bash
# Create Origin Access Control
aws cloudfront create-origin-access-control \
  --origin-access-control-config '{
    "Name": "talentryx-frontend-oac",
    "OriginAccessControlOriginType": "s3",
    "SigningBehavior": "always",
    "SigningProtocol": "sigv4"
  }'
```

Note the `Id` from output, then create the distribution:

```bash
aws cloudfront create-distribution \
  --distribution-config '{
    "CallerReference": "talentryx-frontend-2024",
    "Comment": "Talentryx AI Frontend",
    "Enabled": true,
    "DefaultRootObject": "index.html",
    "Origins": {
      "Quantity": 1,
      "Items": [
        {
          "Id": "S3Origin",
          "DomainName": "talentryx-frontend-976193236457.s3.us-east-1.amazonaws.com",
          "S3OriginConfig": { "OriginAccessIdentity": "" },
          "OriginAccessControlId": "<OAC-Id-from-above>"
        }
      ]
    },
    "DefaultCacheBehavior": {
      "TargetOriginId": "S3Origin",
      "ViewerProtocolPolicy": "redirect-to-https",
      "AllowedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] },
      "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
      "Compress": true
    },
    "CustomErrorResponses": {
      "Quantity": 1,
      "Items": [
        {
          "ErrorCode": 403,
          "ResponsePagePath": "/index.html",
          "ResponseCode": "200",
          "ErrorCachingMinTTL": 0
        }
      ]
    },
    "PriceClass": "PriceClass_100"
  }'
```

Note the `DomainName` (e.g., `d1234abcdef.cloudfront.net`) and `Distribution Id`.

### Step 6 — Grant CloudFront Access to S3

Add bucket policy:

```bash
aws s3api put-bucket-policy \
  --bucket talentryx-frontend-976193236457 \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "AllowCloudFront",
        "Effect": "Allow",
        "Principal": { "Service": "cloudfront.amazonaws.com" },
        "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::talentryx-frontend-976193236457/*",
        "Condition": {
          "StringEquals": {
            "AWS:SourceArn": "arn:aws:cloudfront::976193236457:distribution/<distribution-id>"
          }
        }
      }
    ]
  }'
```

### Step 7 — Update Backend CORS with CloudFront URL

Redeploy backend with the CloudFront domain as `FrontendUrl`:

```bash
cd /mnt/d/shared/trial/ai-behavioral-interviewer-proctoring/serverless

sam build
sam deploy \
  --parameter-overrides "StageName=dev FrontendUrl=https://<cloudfront-domain>.cloudfront.net" \
  --no-confirm-changeset
```

### Step 8 — Rebuild and Redeploy Frontend with Final API URL

Update `serverless/frontend/.env.production` with the confirmed `ApiEndpoint`, then:

```bash
cd serverless/frontend
npm run build
aws s3 sync dist/ s3://talentryx-frontend-976193236457/ --delete
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

---

## Auth Integration (Company Auth via n8n + Frappe CRM)

The register Lambda uses the same pattern as the company's existing auth:

```python
import functools
import boto3

@functools.lru_cache(maxsize=1)
def get_frappe_api_token():
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(
        SecretId='arn:aws:secretsmanager:us-east-1:976193236457:secret:opencrm/frappe-api-key-iQgSaZ'
    )
    secret = response['SecretString'].strip()
    if secret.startswith('token '):
        return secret
    return f'token {secret}'
```

The n8n webhook handles:
- OTP generation and email delivery
- CRM lead creation in OpenCRM/Frappe
- Candidate invite email delivery

No Cognito, no SES — all email goes through n8n webhook with Frappe API authorization.

---

## Smoke Test

After both frontend and backend are deployed:

1. Open `https://<cloudfront-domain>.cloudfront.net`
2. Register as recruiter (enter name, email, mobile)
3. Check email for OTP, verify
4. Create a job
5. Add candidates, upload resumes
6. Analyse resumes against JD
7. Prepare interview and send invite
8. Open candidate link, complete interview
9. Trigger scoring
10. Verify scorecard and report in recruiter dashboard

---

## Redeployment (After Code Changes)

```bash
cd /mnt/d/shared/trial/ai-behavioral-interviewer-proctoring/serverless

# Backend
sam build
sam deploy --no-confirm-changeset

# Frontend
cd frontend
npm run build
aws s3 sync dist/ s3://talentryx-frontend-976193236457/ --delete
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

---

## Cleanup / Delete Stack

```bash
# Empty S3 buckets first (CloudFormation can't delete non-empty buckets)
aws s3 rm s3://talentryx-frontend-976193236457 --recursive
aws s3 rm s3://psysense-dev-artifacts-976193236457 --recursive

# Delete backend stack
aws cloudformation delete-stack --stack-name talentryx-dev --region us-east-1

# Delete CloudFront distribution (disable first, then delete)
aws cloudfront update-distribution --id <distribution-id> --if-match <etag> --distribution-config '...(Enabled: false)...'
# Wait for deployment, then:
aws cloudfront delete-distribution --id <distribution-id> --if-match <new-etag>

# Delete frontend bucket
aws s3 rb s3://talentryx-frontend-976193236457
```

---

## Cost Estimate (Pay-per-use, scales to zero)

| Resource | Estimated Cost |
|---|---|
| Lambda (10 functions) | ~$0.20 per 1000 invocations |
| API Gateway HTTP API | $1.00 per million requests |
| DynamoDB (on-demand) | $1.25 per million writes |
| S3 (artifacts + frontend) | < $1/month |
| CloudFront | Free tier: 1 TB/month |
| Step Functions | $0.025 per 1000 transitions |
| SSM Parameter Store | Free (standard params) |
| Secrets Manager | $0.40/month per secret |
| CloudWatch Logs | $0.50/GB ingested |

**Total for low-traffic MVP: < $5/month**

---

## Security

- Groq API key in SSM SecureString — never in code
- Frappe API key in Secrets Manager — accessed via ARN at runtime
- S3 buckets are private — CloudFront OAC for frontend, pre-signed URLs for artifacts
- No Cognito — company auth via n8n OTP + DynamoDB session tokens
- Audio files auto-expire after 30 days (S3 lifecycle)
- HTTPS enforced via CloudFront
- CORS restricted to CloudFront domain
- Lambda IAM roles follow least-privilege
