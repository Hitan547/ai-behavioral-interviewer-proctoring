# Repository Structure

This repo keeps the production AWS serverless SaaS and the old Streamlit prototype separate.

## Folders

```text
.
+-- serverless/
|   +-- backend/
|   +-- frontend/
|   +-- template.yaml
|   `-- local_server.py
+-- legacy-streamlit/
|   +-- demo_app.py
|   +-- recruiter_dashboard.py
|   +-- answer_service/
|   +-- emotion_service/
|   +-- matching_service/
|   +-- tests/
|   `-- requirements.txt
+-- docs/
+-- tests/
`-- README.md
```

## What Is Production

`serverless/` is the active product path.

Use it for:

- Recruiter signup and login.
- Job creation.
- Resume and JD analysis.
- Candidate invites.
- Candidate credential login.
- Interview flow.
- Proctoring signals.
- Scoring and reports.
- Billing foundation.
- AWS deployment.

Do not rename or move this folder casually because SAM, frontend scripts, tests, local server paths, and deployment notes depend on it.

## What Is Legacy

`legacy-streamlit/` is retained as a historical reference and local prototype.

Use it for:

- Comparing old Streamlit recruiter dashboard behavior.
- Checking old proctoring UI ideas.
- Recovering previous scoring or report ideas.
- Running an old demo when needed.

It is not the AWS deployment target.

## Why This Is Professional

This structure shows a normal product evolution:

1. Prototype in Streamlit.
2. Production rewrite in AWS serverless.
3. Legacy prototype preserved for reference.
4. Active product isolated for deployment.

The old code is not mixed into the production app, so the repo stays readable and safer to deploy.

## Common Commands

Run serverless frontend:

```powershell
cd serverless\frontend
npm.cmd run dev
```

Run serverless local API:

```powershell
cd serverless
python local_server.py
```

Run legacy Streamlit:

```powershell
cd legacy-streamlit
streamlit run demo_app.py
```

Run serverless tests:

```powershell
python -m pytest tests\test_serverless_*.py
```
