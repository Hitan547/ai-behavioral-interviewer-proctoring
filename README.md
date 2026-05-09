# Talentryx AI

AI behavioral interview and proctoring SaaS.

This repository now has a clear split between the active AWS serverless product and the older Streamlit prototype that was used for product discovery.

## Repository Structure

```text
.
+-- serverless/          # Active AWS serverless SaaS app
+-- legacy-streamlit/    # Historical Streamlit prototype and local demo app
+-- docs/                # Architecture, deployment, policy, and migration notes
+-- tests/               # Serverless-focused tests
`-- README.md            # This guide
```

## Active Product

Use `serverless/` for the real SaaS product.

It contains:

- React recruiter and candidate frontend.
- Lambda handler code for jobs, candidates, interviews, scoring, billing, and auth.
- DynamoDB/S3/Cognito/API Gateway/SAM configuration.
- Local development backend for testing without deploying.

AWS production work should stay inside `serverless/` and follow the CEO-approved serverless-only instruction set.

## Legacy Prototype

Use `legacy-streamlit/` only for reference or old demo behavior.

It contains:

- The previous Streamlit app.
- Old local microservices.
- Old Docker/compose deployment files.
- Legacy tests and scripts.

Run the legacy app from inside that folder:

```powershell
cd legacy-streamlit
streamlit run demo_app.py
```

or use:

```powershell
cd legacy-streamlit
.\run_system.bat
```

## Serverless Local Development

Frontend:

```powershell
cd serverless\frontend
npm.cmd install
npm.cmd run dev
```

Backend local API:

```powershell
cd serverless
python local_server.py
```

The local serverless flow uses local development configuration. Deployed secrets belong in AWS SSM Parameter Store, while frontend environment variables must remain limited to `VITE_*` values.

## Deployment Rule

Do not deploy the Streamlit prototype as the production SaaS.

The production direction is:

- AWS SAM/CloudFormation.
- Cognito for auth.
- API Gateway HTTP API.
- Lambda for backend execution.
- DynamoDB for app data.
- S3 for artifacts.
- SSM Parameter Store for secrets.
- n8n webhook for invite email.

Avoid EC2, RDS, VPC, NAT Gateway, Load Balancer, SES, SageMaker, ECS/EKS, OpenSearch, ElastiCache, and Redshift unless the CEO instruction changes.

## More Docs

- [Repository structure](docs/REPOSITORY_STRUCTURE.md)
- [Serverless README](serverless/README.md)
- [Deployment checklist](serverless/DEPLOYMENT_CHECKLIST.md)
- [Branding note](serverless/BRANDING.md)
