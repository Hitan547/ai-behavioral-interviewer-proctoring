# Branding Note

Public product name: Talentryx AI.

This rename is intentionally a public branding change only. Do not rename deployed or local infrastructure identifiers unless a separate migration is planned and approved.

Keep these legacy internal identifiers stable for now:

- SAM logical resource names such as `PsySenseTable`.
- Physical AWS names using the `psysense-` prefix.
- SSM parameter paths such as `/psysense/dev/GROQ_API_KEY`.
- DynamoDB local table name `psysense-local`.
- Browser localStorage keys such as `psysense.accessToken`.
- Existing candidate passwords that start with `PS-`.

New candidate invite passwords use the `TX-` prefix. Existing `PS-` credentials remain valid because candidate login checks the stored password value exactly.

Before a production rebrand of AWS resources, create a migration plan for DynamoDB data, S3 artifacts, Cognito users, SSM parameters, CloudFormation stack names, n8n webhook templates, and frontend environment variables.
