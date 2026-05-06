# Safe AWS Dev Deployment Checklist

This checklist is for the PsySense serverless MVP only.

Do not deploy the old EC2/RDS/OpenSearch/Docker architecture to AWS.

## CEO Cost Guardrail

Allowed AWS services:

- Lambda
- API Gateway
- DynamoDB
- S3
- SNS
- SQS
- EventBridge
- Step Functions
- Cognito
- Amplify
- AppSync
- Bedrock
- CloudFormation
- CloudWatch
- SSM Parameter Store

Do not create:

- VPC
- EC2
- RDS
- OpenSearch
- SageMaker
- ECS/EKS
- NAT Gateway
- Load Balancer
- ElastiCache
- Redshift

## Important Product Reality

The current serverless stack covers the backend MVP:

1. Recruiter creates jobs.
2. Recruiter creates candidates.
3. Candidate resume is uploaded to S3.
4. Resume is used to prepare questions.
5. Candidate answers are submitted.
6. Integrity signals are stored.
7. Scoring runs through Step Functions.
8. Recruiter result is saved.
9. Recruiter PDF report is generated to S3.

The current serverless stack does not yet fully migrate the browser interview experience from the local Streamlit app.

That means the following local-demo features still need frontend/serverless migration before the full interview experience works on AWS:

- Candidate web interview UI.
- Live camera preview.
- WebRTC/browser media handling.
- Browser-side audio recording.
- Speech-to-text upload/transcription flow.
- Full proctoring event capture from the browser.
- Recruiter dashboard frontend connected to the new APIs.

For the first AWS dev deployment, treat this as a backend MVP validation, not a complete production interview website.

## Prerequisites

Install or confirm:

- AWS CLI v2
- AWS SAM CLI
- Python 3.11
- Docker Desktop, only for local SAM build if needed

PowerShell checks:

```powershell
aws --version
sam --version
python --version
docker --version
```

## Confirm AWS Identity

```powershell
aws sts get-caller-identity
```

Expected:

- Command succeeds.
- Account ID is the approved company AWS account.
- User/role is the one CEO approved for this dev deployment.

## Check Required Permissions

Run these read-only checks first:

```powershell
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE
aws lambda list-functions
aws apigatewayv2 get-apis
aws dynamodb list-tables
aws s3 ls
aws sqs list-queues
aws stepfunctions list-state-machines
aws cognito-idp list-user-pools --max-results 10
aws logs describe-log-groups --limit 5
aws events list-rules --limit 5
aws ssm describe-parameters --max-results 5
```

If any command returns `AccessDenied` or `UnauthorizedOperation`, ask the CEO/admin for that specific permission before deployment.

## Store Groq API Key In SSM

Do not commit the real key.

```powershell
aws ssm put-parameter `
  --name "/psysense/dev/GROQ_API_KEY" `
  --type "SecureString" `
  --value "PASTE_GROQ_KEY_HERE" `
  --overwrite
```

Verify the parameter exists without printing the secret:

```powershell
aws ssm get-parameter `
  --name "/psysense/dev/GROQ_API_KEY" `
  --with-decryption `
  --query "Parameter.Name"
```

## Local Template Validation

From repo root:

```powershell
Set-Location "C:\Users\Hitan\OneDrive\Documents\GitHub\ai-behavioral-interviewer-proctoring"
sam validate --template-file serverless/template.yaml
sam build --template-file serverless/template.yaml
```

Inspect generated template for blocked services:

```powershell
Select-String -Path ".aws-sam\build\template.yaml" `
  -Pattern "AWS::EC2|AWS::RDS|AWS::OpenSearchService|AWS::SageMaker|AWS::ECS|AWS::EKS|ElasticLoadBalancing|ElastiCache|Redshift|NatGateway|LoadBalancer|DBInstance|Domain"
```

Expected:

- No matches.

Also inspect the source template:

```powershell
Select-String -Path "serverless\template.yaml" `
  -Pattern "AWS::EC2|AWS::RDS|AWS::OpenSearchService|AWS::SageMaker|AWS::ECS|AWS::EKS|ElasticLoadBalancing|ElastiCache|Redshift|NatGateway|LoadBalancer|DBInstance|Domain"
```

Expected:

- No matches.

## Optional Guided Deployment

Only run this after CEO/admin approval for first dev deployment.

```powershell
sam deploy --guided `
  --template-file ".aws-sam\build\template.yaml" `
  --stack-name "psysense-dev-serverless" `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    StageName=dev `
    GroqApiKeyParameterName=/psysense/dev/GROQ_API_KEY
```

Suggested guided answers:

- AWS Region: approved region, for example `us-east-1`.
- Confirm changes before deploy: `Y`.
- Allow SAM CLI IAM role creation: `Y`.
- Disable rollback: `N`.
- Save arguments to config file: `Y`.

## Safer Non-Guided Deployment After First Config

After `samconfig.toml` exists:

```powershell
sam deploy
```

## Post-Deployment Checks

Get stack outputs:

```powershell
aws cloudformation describe-stacks `
  --stack-name "psysense-dev-serverless" `
  --query "Stacks[0].Outputs"
```

Confirm only allowed resources were created:

```powershell
aws cloudformation list-stack-resources `
  --stack-name "psysense-dev-serverless" `
  --query "StackResourceSummaries[].ResourceType"
```

Expected resource types include only approved serverless resources such as:

- `AWS::Lambda::Function`
- `AWS::ApiGatewayV2::Api`
- `AWS::DynamoDB::Table`
- `AWS::S3::Bucket`
- `AWS::SQS::Queue`
- `AWS::StepFunctions::StateMachine`
- `AWS::Cognito::UserPool`
- `AWS::Events::Rule`
- `AWS::CloudWatch::LogGroup`
- IAM roles/policies created by SAM for these services

If any blocked service appears, stop and delete the stack immediately.

## Smoke Test Order

Use the API Gateway URL from stack outputs.

The API is Cognito-protected, so first create or configure a Cognito test user with:

- `custom:org_id`
- `custom:role`

Then test this backend flow:

1. `POST /jobs`
2. `GET /jobs`
3. `POST /jobs/{jobId}/candidates`
4. Upload resume PDF using the returned S3 presigned URL.
5. `POST /jobs/{jobId}/candidates/{candidateId}/prepare-interview`
6. `GET /jobs/{jobId}/candidates/{candidateId}/interview`
7. `POST /jobs/{jobId}/candidates/{candidateId}/interview`
8. `POST /jobs/{jobId}/candidates/{candidateId}/score`
9. Wait for Step Functions execution.
10. `GET /jobs/{jobId}/candidates/{candidateId}/result`
11. Open the returned `reportDownload.url`.

## CEO Approval Message

Send this before first deployment:

> I will deploy only the approved PsySense AWS serverless dev stack using CloudFormation/SAM. It creates Lambda, API Gateway, DynamoDB, S3, SQS, Step Functions, Cognito, CloudWatch/EventBridge resources, and SSM parameter references. It does not create VPC, EC2, RDS, OpenSearch, SageMaker, ECS/EKS, NAT Gateway, Load Balancer, ElastiCache, or Redshift. This first deployment validates the backend MVP; the full browser interview/WebRTC frontend still needs a separate serverless frontend migration.

