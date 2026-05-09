"""Talentryx AI Local Development Server.

Wraps the EXACT same Lambda handler code in a Flask server so you can
test locally without AWS permissions. When ready to deploy, run `sam deploy`
— the handler code is identical.

Mocks provided:
  - DynamoDB  → DynamoDB Local (Docker)
  - S3        → Local filesystem (_local_artifacts/)
  - SSM       → Environment variables / .env file
  - SES       → Console log (no real email sent)
  - StepFn    → Direct call to scoring_worker.handler()

Usage:
    pip install flask flask-cors boto3 PyPDF2 python-dotenv
    docker run -d -p 8000:8000 amazon/dynamodb-local
    python local_server.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Add backend to Python path so handlers can import normally
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from flask import Flask, jsonify, request, send_file  # noqa: E402

app = Flask(__name__)
app.url_map.strict_slashes = False

# ── Load .env if available ──
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.isfile(_env_path):
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(_env_path)
        print(f"  ✓ Loaded .env from {_env_path}")
    except ImportError:
        # Manual fallback — read KEY=VALUE lines
        with open(_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        print(f"  ✓ Loaded .env (manual parse) from {_env_path}")

# ── Config ──
DYNAMODB_LOCAL_ENDPOINT = os.environ.get("DYNAMODB_LOCAL_ENDPOINT", "http://localhost:8000")
TABLE_NAME = os.environ.get("TABLE_NAME", "psysense-local")
ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "_local_artifacts")
LOCAL_PORT = int(os.environ.get("LOCAL_PORT", "3001"))

_root_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, ".env"))
if os.path.isfile(_root_env_path):
    try:
        from dotenv import load_dotenv as _load_root_dotenv  # type: ignore
        _load_root_dotenv(_root_env_path, override=False)
        print(f"  Loaded root .env defaults from {_root_env_path}")
    except ImportError:
        with open(_root_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        print(f"  Loaded root .env defaults (manual parse) from {_root_env_path}")

# Set environment variables that Lambda handlers expect
os.environ["TABLE_NAME"] = TABLE_NAME
os.environ["ARTIFACT_BUCKET"] = "local-artifacts"
os.environ["ENVIRONMENT"] = "local"
os.environ["FRONTEND_URL"] = os.environ.get("FRONTEND_URL", "http://localhost:5173")
os.environ["GROQ_API_KEY_PARAMETER_NAME"] = os.environ.get(
    "GROQ_API_KEY_PARAMETER_NAME", "/psysense/dev/GROQ_API_KEY"
)
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
# Scoring: set a fake ARN so the handler doesn't crash before we intercept
os.environ.setdefault("SCORING_WORKFLOW_ARN", "arn:aws:states:local:000000000000:stateMachine:local-scoring")


# ── DynamoDB Setup (moto in-memory OR DynamoDB Local Docker) ──
_moto_mock = None  # Keep reference so the mock stays active
_using_moto = False  # Track which DynamoDB backend is active


def setup_dynamodb():
    """Set up DynamoDB — tries Docker first, falls back to moto in-memory."""
    global _moto_mock, _using_moto

    # Try DynamoDB Local (Docker) first — with a fast timeout
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(DYNAMODB_LOCAL_ENDPOINT)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8000
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((host, port))
        sock.close()

        import boto3
        ddb = boto3.resource(
            "dynamodb",
            endpoint_url=DYNAMODB_LOCAL_ENDPOINT,
            region_name="us-east-1",
            aws_access_key_id="local",
            aws_secret_access_key="local",
        )
        table = ddb.Table(TABLE_NAME)
        try:
            table.load()
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if code != "ResourceNotFoundException":
                raise
            table = ddb.create_table(
                TableName=TABLE_NAME,
                KeySchema=[
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "pk", "AttributeType": "S"},
                    {"AttributeName": "sk", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            table.wait_until_exists()
        print(f"  ✓ DynamoDB Local (Docker) — table '{TABLE_NAME}' ({table.item_count} items)")
        _using_moto = False
        return table
    except Exception:
        pass

    # Fall back to moto in-memory mock
    print("  ⚠ DynamoDB Local not available — using moto in-memory mock")
    try:
        from moto import mock_aws
        _moto_mock = mock_aws()
        _moto_mock.start()
    except ImportError:
        from moto import mock_dynamodb
        _moto_mock = mock_dynamodb()
        _moto_mock.start()

    _using_moto = True  # Must be set BEFORE boto3 calls so the patch skips endpoint_url
    import boto3
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    table = ddb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.wait_until_exists()
    print(f"  ✓ DynamoDB (moto in-memory) — table '{TABLE_NAME}' created")
    print("    ⚠ Data will NOT persist across restarts")
    return table


# ══════════════════════════════════════════════════════════════
#  boto3 monkey-patching — intercept ALL AWS service calls
# ══════════════════════════════════════════════════════════════

class _LocalS3Client:
    """Filesystem-backed S3 mock. Supports the operations our repos use."""

    def __init__(self, root: str):
        self._root = root

    def _path(self, bucket: str, key: str) -> str:
        # Flatten bucket into root (we only have one logical bucket locally)
        return os.path.join(self._root, key.replace("/", os.sep))

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **kwargs):
        path = self._path(Bucket, Key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(Body if isinstance(Body, bytes) else Body.encode("utf-8"))
        return {"ETag": '"local"'}

    def get_object(self, *, Bucket: str, Key: str, **kwargs):
        path = self._path(Bucket, Key)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Local S3 mock: file not found: {path}")

        class _Body:
            def __init__(self, filepath):
                self._filepath = filepath
            def read(self):
                with open(self._filepath, "rb") as f:
                    return f.read()

        return {"Body": _Body(path), "ContentType": "application/octet-stream"}

    def generate_presigned_url(self, ClientMethod: str, Params: dict, ExpiresIn: int = 900, HttpMethod: str = "GET"):
        key = Params.get("Key", "")
        content_type = Params.get("ContentType", "application/octet-stream")
        if ClientMethod == "put_object":
            return f"http://localhost:{LOCAL_PORT}/local-upload/{key}?contentType={content_type}"
        else:
            return f"http://localhost:{LOCAL_PORT}/local-download/{key}"


class _LocalSSMClient:
    """Returns API keys from environment variables instead of AWS SSM."""

    def get_parameter(self, *, Name: str, WithDecryption: bool = False, **kwargs):
        # Map SSM parameter names to environment variable values
        mappings = {
            os.environ.get("GROQ_API_KEY_PARAMETER_NAME", ""): os.environ.get("GROQ_API_KEY", ""),
            os.environ.get("N8N_INVITE_WEBHOOK_PARAMETER_NAME", ""): os.environ.get("N8N_INVITE_WEBHOOK", ""),
            os.environ.get("N8N_RESULT_WEBHOOK_PARAMETER_NAME", ""): os.environ.get("N8N_RESULT_WEBHOOK", ""),
            os.environ.get("RAZORPAY_KEY_ID_PARAMETER_NAME", ""): os.environ.get("RAZORPAY_KEY_ID", ""),
            os.environ.get("RAZORPAY_KEY_SECRET_PARAMETER_NAME", ""): os.environ.get("RAZORPAY_KEY_SECRET", ""),
        }
        value = mappings.get(Name, "")
        if not value:
            print(f"  ⚠ SSM mock: no value for parameter '{Name}' — set it in .env")
        return {"Parameter": {"Name": Name, "Value": value, "Type": "SecureString"}}


class _LocalSESClient:
    """Logs emails to console instead of sending via SES."""

    def send_email(self, *, Source: str, Destination: dict, Message: dict, **kwargs):
        to_list = Destination.get("ToAddresses", [])
        subject = Message.get("Subject", {}).get("Data", "(no subject)")
        print("\n  📧 SES MOCK — Email sent:")
        print(f"     From:    {Source}")
        print(f"     To:      {', '.join(to_list)}")
        print(f"     Subject: {subject}")
        print("     (Body logged to console, not actually sent)\n")
        return {"MessageId": f"local-{int(time.time())}"}

    def send_raw_email(self, **kwargs):
        print("\n  📧 SES MOCK — Raw email sent (logged, not delivered)\n")
        return {"MessageId": f"local-raw-{int(time.time())}"}


class _LocalStepFunctionsClient:
    """Calls scoring_worker.handler() directly instead of starting a state machine."""

    def start_execution(self, *, stateMachineArn: str, input: str, **kwargs):
        print("\n  ⚡ StepFunctions MOCK — calling scoring_worker directly...")
        payload = json.loads(input)
        from handlers.scoring_worker import handler as scoring_worker_handler
        try:
            result = scoring_worker_handler(payload, None)
            print(f"  ⚡ Scoring complete: score={result.get('result', {}).get('finalScore', '?')}\n")
        except Exception as e:
            print(f"  ⚡ Scoring worker error: {e}\n")
        return {
            "executionArn": f"arn:aws:states:local:000000000000:execution:local:{int(time.time())}",
            "startDate": str(time.time()),
        }


def _patch_boto3_for_local():
    """Monkey-patch boto3 to intercept ALL AWS service calls."""
    import boto3

    local_s3 = _LocalS3Client(ARTIFACT_DIR)
    local_ssm = _LocalSSMClient()
    local_ses = _LocalSESClient()
    local_sfn = _LocalStepFunctionsClient()

    _original_resource = boto3.resource
    _original_client = boto3.client

    def patched_resource(service_name, *args, **kwargs):
        if service_name == "dynamodb" and not _using_moto:
            kwargs["endpoint_url"] = DYNAMODB_LOCAL_ENDPOINT
            kwargs["region_name"] = "us-east-1"
            kwargs["aws_access_key_id"] = "local"
            kwargs["aws_secret_access_key"] = "local"
        return _original_resource(service_name, *args, **kwargs)

    def patched_client(service_name, *args, **kwargs):
        if service_name == "dynamodb" and not _using_moto:
            kwargs["endpoint_url"] = DYNAMODB_LOCAL_ENDPOINT
            kwargs["region_name"] = "us-east-1"
            kwargs["aws_access_key_id"] = "local"
            kwargs["aws_secret_access_key"] = "local"
            return _original_client(service_name, *args, **kwargs)
        if service_name == "s3":
            return local_s3
        if service_name == "ssm":
            return local_ssm
        if service_name == "ses":
            return local_ses
        if service_name == "stepfunctions":
            return local_sfn
        # Fallback: let it through (will use real AWS or fail gracefully)
        return _original_client(service_name, *args, **kwargs)

    boto3.resource = patched_resource
    boto3.client = patched_client


# ── Mock identity for local dev (no Cognito) ──
LOCAL_IDENTITY = {
    "sub": "local-user-001",
    "email": "recruiter@talentryx.local",
    "custom:org_id": "local-org",
    "custom:role": "recruiter",
}

LOCAL_RECRUITERS = {
    "recruiter@talentryx.local": {
        "password": "Talentryx@123",
        "orgId": "local-org",
        "orgName": "Talentryx Local Org",
        "userId": "local-user-001",
    },
    "recruiter@psysense.local": {
        "password": "PsySense@123",
        "orgId": "local-org",
        "orgName": "Talentryx Local Org",
        "userId": "local-user-001",
    }
}
LOCAL_AUTH_TOKENS: dict[str, dict] = {}


def _claims_for_local_token(token: str) -> dict | None:
    if token == "local-dev-token":
        return LOCAL_IDENTITY
    return LOCAL_AUTH_TOKENS.get(token)


def _new_local_recruiter_token(email: str, account: dict) -> str:
    import secrets

    token = f"local-recruiter-{secrets.token_urlsafe(24)}"
    LOCAL_AUTH_TOKENS[token] = {
        "sub": account["userId"],
        "email": email,
        "custom:org_id": account["orgId"],
        "custom:role": "recruiter",
    }
    return token


def flask_to_lambda_event(path_params: dict | None = None) -> dict:
    """Convert a Flask request into an API Gateway v2 Lambda event."""
    body = request.get_data(as_text=True) or "{}"
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header.replace("Bearer ", "", 1).strip() if auth_header.startswith("Bearer ") else ""
    claims = _claims_for_local_token(bearer) or LOCAL_IDENTITY
    return {
        "version": "2.0",
        "routeKey": f"{request.method} {request.path}",
        "rawPath": request.path,
        "requestContext": {
            "http": {
                "method": request.method,
                "path": request.path,
            },
            "authorizer": {
                "jwt": {
                    "claims": claims,
                }
            },
        },
        "headers": dict(request.headers),
        "pathParameters": path_params or {},
        "body": body,
        "isBase64Encoded": False,
    }


def lambda_response_to_flask(result: dict):
    """Convert a Lambda proxy response to a Flask response."""
    status = result.get("statusCode", 200)
    body = result.get("body", "{}")
    headers = result.get("headers", {})
    resp = app.make_response((body, status))
    for k, v in headers.items():
        resp.headers[k] = v
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return resp


@app.route("/auth/recruiter-signup", methods=["POST", "OPTIONS"])
def recruiter_signup_route():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or body.get("username") or "").strip().lower()
    password = str(body.get("password") or "").strip()
    org_name = str(body.get("orgName") or body.get("org_name") or "Local Demo Org").strip()
    if not email or "@" not in email:
        return jsonify({"error": "Valid recruiter email is required."}), 400
    if len(password) < 8 or not any(ch.isdigit() for ch in password):
        return jsonify({"error": "Password must be at least 8 characters and include a number."}), 400
    if email in LOCAL_RECRUITERS:
        return jsonify({"error": "Recruiter already exists. Use Recruiter Login."}), 409

    safe_org = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-") or "local-demo"
    org_id = f"{safe_org}-{len(LOCAL_RECRUITERS) + 1}"
    account = {
        "password": password,
        "orgId": org_id,
        "orgName": org_name,
        "userId": f"local-user-{len(LOCAL_RECRUITERS) + 1:03d}",
    }
    LOCAL_RECRUITERS[email] = account
    token = _new_local_recruiter_token(email, account)
    return jsonify({
        "accessToken": token,
        "idToken": token,
        "orgId": org_id,
        "role": "recruiter",
        "username": email,
        "orgName": org_name,
    }), 201


@app.route("/auth/recruiter-login", methods=["POST", "OPTIONS"])
def recruiter_login_route():
    if request.method == "OPTIONS":
        return "", 204
    body = request.get_json(silent=True) or {}
    email = str(body.get("email") or body.get("username") or "").strip().lower()
    password = str(body.get("password") or "").strip()
    account = LOCAL_RECRUITERS.get(email)
    if not account or account.get("password") != password:
        return jsonify({"error": "Recruiter credentials are invalid."}), 401
    token = _new_local_recruiter_token(email, account)
    return jsonify({
        "accessToken": token,
        "idToken": token,
        "orgId": account["orgId"],
        "role": "recruiter",
        "username": email,
        "orgName": account["orgName"],
    })


# ── CORS preflight ──
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


# ══════════════════════════════════════════════════════════════
#  Routes that map to Lambda handlers
# ══════════════════════════════════════════════════════════════

# Jobs
@app.route("/jobs", methods=["GET", "POST", "OPTIONS"])
def jobs_route():
    if request.method == "OPTIONS":
        return "", 204
    from handlers.jobs import handler
    event = flask_to_lambda_event()
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Single job operations (close job, get stats)
@app.route("/jobs/<job_id>", methods=["GET", "PUT", "OPTIONS"])
def single_job_route(job_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.jobs import handler
    event = flask_to_lambda_event({"jobId": job_id})
    event["rawPath"] = f"/jobs/{job_id}"
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Job stats
@app.route("/jobs/<job_id>/stats", methods=["GET", "OPTIONS"])
def job_stats_route(job_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.jobs import handler
    event = flask_to_lambda_event({"jobId": job_id})
    event["rawPath"] = f"/jobs/{job_id}/stats"
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Candidates
@app.route("/jobs/<job_id>/candidates", methods=["GET", "POST", "OPTIONS"])
def candidates_route(job_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidates import handler
    event = flask_to_lambda_event({"jobId": job_id})
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Update candidate / view single candidate
@app.route("/jobs/<job_id>/candidates/<candidate_id>", methods=["GET", "PUT", "OPTIONS"])
def update_candidate_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidates import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    event["rawPath"] = f"/jobs/{job_id}/candidates/{candidate_id}"
    result = handler(event, None)
    return lambda_response_to_flask(result)


@app.route("/jobs/<job_id>/candidates/<candidate_id>/invite", methods=["PUT", "OPTIONS"])
def invite_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidates import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    event["rawPath"] = f"/jobs/{job_id}/candidates/{candidate_id}/invite"
    result = handler(event, None)
    return lambda_response_to_flask(result)


@app.route("/jobs/<job_id>/candidates/<candidate_id>/retest", methods=["POST", "OPTIONS"])
def retest_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidates import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    event["rawPath"] = f"/jobs/{job_id}/candidates/{candidate_id}/retest"
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Prepare interview
@app.route("/jobs/<job_id>/candidates/<candidate_id>/prepare-interview", methods=["POST", "OPTIONS"])
def prepare_interview_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.prepare_interview import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Candidate interview (get/submit)
@app.route("/jobs/<job_id>/candidates/<candidate_id>/interview", methods=["GET", "POST", "OPTIONS"])
def interview_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidate_interview import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Audio upload URL — now goes through the REAL handler (S3 is mocked)
@app.route("/jobs/<job_id>/candidates/<candidate_id>/audio-upload-url", methods=["POST", "OPTIONS"])
def audio_upload_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidate_interview import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    event["rawPath"] = f"/jobs/{job_id}/candidates/{candidate_id}/audio-upload-url"
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Local file upload endpoint (handles presigned URL PUT requests from S3 mock)
@app.route("/local-upload/<path:key>", methods=["PUT", "OPTIONS"])
def local_upload(key):
    if request.method == "OPTIONS":
        return "", 204
    filepath = os.path.join(ARTIFACT_DIR, key.replace("/", os.sep))
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(request.get_data())
    print(f"  📁 Local upload: {filepath} ({len(request.get_data())} bytes)")
    return jsonify({"message": "Uploaded", "path": filepath})


# Local file download endpoint (handles presigned URL GET requests from S3 mock)
@app.route("/local-download/<path:key>", methods=["GET", "OPTIONS"])
def local_download(key):
    if request.method == "OPTIONS":
        return "", 204
    filepath = os.path.join(ARTIFACT_DIR, key.replace("/", os.sep))
    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath)


# Transcribe
@app.route("/jobs/<job_id>/candidates/<candidate_id>/questions/<int:q_idx>/transcribe", methods=["POST", "OPTIONS"])
def transcribe_route(job_id, candidate_id, q_idx):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidate_interview import handler
    event = flask_to_lambda_event({
        "jobId": job_id, "candidateId": candidate_id, "questionIndex": str(q_idx),
    })
    event["rawPath"] = f"/jobs/{job_id}/candidates/{candidate_id}/questions/{q_idx}/transcribe"
    result = handler(event, None)
    return lambda_response_to_flask(result)


@app.route("/transcribe-practice", methods=["POST", "OPTIONS"])
def practice_transcribe_route():
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidate_interview import handler
    event = flask_to_lambda_event()
    event["rawPath"] = "/transcribe-practice"
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Scoring
@app.route("/jobs/<job_id>/candidates/<candidate_id>/score", methods=["POST", "OPTIONS"])
def score_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.scoring import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Get result
@app.route("/jobs/<job_id>/candidates/<candidate_id>/result", methods=["GET", "OPTIONS"])
def result_route(job_id, candidate_id):
    if request.method == "OPTIONS":
        return "", 204
    from handlers.scoring import handler
    event = flask_to_lambda_event({"jobId": job_id, "candidateId": candidate_id})
    event["rawPath"] = f"/jobs/{job_id}/candidates/{candidate_id}/result"
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Analyse resumes
@app.route("/jobs/<job_id>/analyse-resumes", methods=["POST", "OPTIONS"])
def analyse_resumes_route(job_id):
    if request.method == "OPTIONS":
        return "", 204
    # Check if handler exists; if not, return a stub response
    try:
        from handlers.analyse_resumes import handler
        event = flask_to_lambda_event({"jobId": job_id})
        result = handler(event, None)
        return lambda_response_to_flask(result)
    except ImportError:
        return jsonify({
            "results": [],
            "_note": "analyse_resumes handler not yet implemented",
        })


@app.route("/auth/candidate-login", methods=["POST", "OPTIONS"])
def candidate_login_route():
    if request.method == "OPTIONS":
        return "", 204
    from handlers.candidate_auth import handler
    event = flask_to_lambda_event()
    result = handler(event, None)
    return lambda_response_to_flask(result)


@app.route("/billing", methods=["GET", "OPTIONS"])
def billing_route():
    if request.method == "OPTIONS":
        return "", 204
    from handlers.billing import handler
    event = flask_to_lambda_event()
    result = handler(event, None)
    return lambda_response_to_flask(result)


# Health check
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "mode": "local",
        "table": TABLE_NAME,
        "n8nInviteConfigured": bool(os.environ.get("N8N_INVITE_WEBHOOK", "").strip()),
    })


# ── Startup ──
if __name__ == "__main__":
    print()
    print("  ╔════════════════════════════════════════════════════╗")
    print("  ║  Talentryx AI Local Development Server            ║")
    print("  ║  Same code as AWS Lambda — with full local mocks  ║")
    print("  ╚════════════════════════════════════════════════════╝")
    print()

    _patch_boto3_for_local()

    # Verify mocked services
    _groq_key = os.environ.get("GROQ_API_KEY", "")
    if _groq_key:
        print(f"  ✓ GROQ_API_KEY loaded ({_groq_key[:8]}...)")
    else:
        print("  ⚠ GROQ_API_KEY not set — question generation will use defaults")
        print("    → Add GROQ_API_KEY=gsk_... to serverless/.env")

    print(f"  ✓ S3 mock     → {ARTIFACT_DIR}")
    print("  ✓ SSM mock    → reads from environment / .env")
    print("  ✓ SES mock    → logs to console")
    print("  ✓ StepFn mock → calls scoring_worker directly")

    setup_dynamodb()

    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    print(f"  ✓ API server → http://localhost:{LOCAL_PORT}")
    print(f"  ✓ Frontend   → {os.environ.get('FRONTEND_URL', 'http://localhost:5173')}")
    print()

    debug_enabled = os.environ.get("LOCAL_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=LOCAL_PORT, debug=debug_enabled, use_reloader=False)
