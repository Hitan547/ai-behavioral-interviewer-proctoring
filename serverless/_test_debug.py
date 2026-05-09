"""Debug script to find the GET /jobs 500 error."""
import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
os.environ["TABLE_NAME"] = "psysense-local"
os.environ["ENVIRONMENT"] = "test"  # Let exceptions propagate
os.environ["ARTIFACT_BUCKET"] = "local"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["SCORING_WORKFLOW_ARN"] = "arn:aws:states:local:000000000000:stateMachine:local-scoring"
os.environ["FRONTEND_URL"] = "http://localhost:5173"
os.environ["GROQ_API_KEY_PARAMETER_NAME"] = "/psysense/dev/GROQ_API_KEY"

import boto3
# Point DynamoDB to local
_orig_resource = boto3.resource
def patched_resource(service_name, *args, **kwargs):
    if service_name == "dynamodb":
        kwargs["endpoint_url"] = "http://localhost:8000"
        kwargs["region_name"] = "us-east-1"
        kwargs["aws_access_key_id"] = "local"
        kwargs["aws_secret_access_key"] = "local"
    return _orig_resource(service_name, *args, **kwargs)
boto3.resource = patched_resource

# Test 1: Raw DynamoDB query
print("=" * 60)
print("TEST 1: Direct DynamoDB query for jobs")
print("=" * 60)
ddb = boto3.resource("dynamodb")
table = ddb.Table("psysense-local")
try:
    response = table.query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": "ORG#local-org",
            ":prefix": "JOB#",
        },
        ScanIndexForward=False,
    )
    items = response.get("Items", [])
    print(f"Found {len(items)} items")
    for i, item in enumerate(items[:5]):
        print(f"  Item {i}: pk={item.get('pk')}, sk={item.get('sk')}")
        print(f"    title={item.get('title')}, entityType={item.get('entityType')}")
        print(f"    keys: {list(item.keys())}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()

# Test 2: Call the handler directly
print()
print("=" * 60)
print("TEST 2: Call jobs handler (GET) directly")
print("=" * 60)
from handlers.jobs import handler

event = {
    "version": "2.0",
    "routeKey": "GET /jobs",
    "rawPath": "/jobs",
    "requestContext": {
        "http": {"method": "GET", "path": "/jobs"},
        "authorizer": {
            "jwt": {
                "claims": {
                    "sub": "local-user-001",
                    "email": "recruiter@psysense.local",
                    "custom:org_id": "local-org",
                    "custom:role": "recruiter",
                }
            }
        },
    },
    "headers": {},
    "pathParameters": {},
    "body": "{}",
    "isBase64Encoded": False,
}

try:
    result = handler(event, None)
    print(f"Status: {result.get('statusCode')}")
    print(f"Body: {result.get('body', '')[:500]}")
except Exception as e:
    print(f"EXCEPTION: {e}")
    traceback.print_exc()

# Test 3: Scan all items in table
print()
print("=" * 60)
print("TEST 3: Full table scan (first 20 items)")
print("=" * 60)
try:
    scan = table.scan(Limit=20)
    for i, item in enumerate(scan.get("Items", [])):
        pk = item.get("pk", "?")
        sk = item.get("sk", "?")
        et = item.get("entityType", "?")
        print(f"  [{i}] pk={pk}  sk={sk}  entityType={et}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
