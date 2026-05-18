# Public Frontend Deployment

## Goal

Host the React/Vite frontend on a public HTTPS URL so recruiters and candidates can use Talentryx AI without localhost.

Recommended path:

```text
S3 private bucket -> CloudFront HTTPS distribution -> React app
```

Do not use plain S3 website hosting for the candidate interview flow because camera/microphone/proctoring behavior should run over HTTPS.

## Current Blocker

S3 bucket creation succeeded, but CloudFront deployment is blocked by IAM permissions.

Required CloudFront actions:

```text
cloudfront:ListOriginAccessControls
cloudfront:CreateOriginAccessControl
cloudfront:GetOriginAccessControl
cloudfront:ListDistributions
cloudfront:CreateDistribution
cloudfront:GetDistribution
cloudfront:GetDistributionConfig
cloudfront:UpdateDistribution
cloudfront:CreateInvalidation
```

Required S3 actions:

```text
s3:PutObject
s3:DeleteObject
s3:ListBucket
s3:GetBucketPolicy
s3:PutBucketPolicy
s3:PutPublicAccessBlock
```

Target bucket:

```text
talentryx-dev-frontend-976193236457
```

## Deployment Flow

1. Build frontend:

```powershell
cd serverless\frontend
npm.cmd run build
```

2. Upload `serverless/frontend/dist` to the private frontend S3 bucket.

3. Create or reuse a CloudFront distribution with:

- S3 origin.
- Origin Access Control.
- Redirect HTTP to HTTPS.
- Default root object `index.html`.
- SPA fallback from 403/404 to `/index.html`.

4. Get CloudFront URL:

```text
https://dxxxxx.cloudfront.net
```

5. Redeploy backend with the new frontend URL:

```powershell
sam deploy `
  --template-file serverless\.aws-sam\build\template.yaml `
  --stack-name talentryx-dev `
  --region us-east-1 `
  --resolve-s3 `
  --s3-prefix talentryx-dev `
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND `
  --parameter-overrides `
    StageName=dev `
    GroqApiKeyParameterName=/psysense/dev/GROQ_API_KEY `
    N8nInviteWebhookParameterName=/psysense/dev/N8N_INVITE_WEBHOOK `
    N8nResultWebhookParameterName=/psysense/dev/N8N_RESULT_WEBHOOK `
    RazorpayKeyIdParameterName=/psysense/dev/RAZORPAY_KEY_ID `
    RazorpayKeySecretParameterName=/psysense/dev/RAZORPAY_KEY_SECRET `
    FrontendUrl=https://dxxxxx.cloudfront.net
```

6. Rebuild frontend if API/Cognito env values change.

7. Smoke test from the public URL.

## Custom Domain Later

CloudFront gives a generated domain first. A branded URL can be added later:

```text
https://app.talentryx.ai
https://demo.talentryx.ai
```

That requires:

- Domain/DNS access.
- ACM certificate in `us-east-1`.
- CloudFront alternate domain name.
- Backend redeploy with `FrontendUrl` set to the branded URL.

