"""Check current AWS state before deployment."""
import boto3

cf = boto3.client("cloudformation", region_name="us-east-1")
iam = boto3.client("iam", region_name="us-east-1")

# 1. Check if any psysense stack exists
print("=== STACK STATUS ===")
try:
    resp = cf.describe_stacks(StackName="psysense-dev")
    for s in resp["Stacks"]:
        print(f"  Stack: {s['StackName']}  Status: {s['StackStatus']}")
        if s.get("StackStatusReason"):
            print(f"  Reason: {s['StackStatusReason']}")
except cf.exceptions.ClientError as e:
    if "does not exist" in str(e):
        print("  No psysense-dev stack exists. Clean slate!")
    else:
        print(f"  Error: {e}")

# 2. Check for orphaned IAM roles from the retained resources
print("\n=== ORPHANED IAM ROLES ===")
role_names = [
    "CandidateInterviewFunctionRole",
    "JobsFunctionRole",
    "ScoringWorkerFunctionRole",
    "PrepareInterviewFunctionRole",
    "CandidatesFunctionRole",
]
for role_prefix in role_names:
    try:
        # SAM names roles like: psysense-dev-CandidateInterviewFunctionRole-XXXX
        paginator = iam.get_paginator("list_roles")
        for page in paginator.paginate():
            for role in page["Roles"]:
                if "psysense" in role["RoleName"] and role_prefix.replace("Role","") in role["RoleName"]:
                    print(f"  FOUND orphan: {role['RoleName']}")
        break  # Only need to paginate once
    except Exception as e:
        print(f"  Cannot check IAM roles: {e}")
        break

# 3. Test IAM CreateRole permission
print("\n=== IAM PERMISSION TEST ===")
try:
    iam.create_role(
        RoleName="psysense-test-perm-check",
        AssumeRolePolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}',
    )
    print("  iam:CreateRole = ALLOWED")
    iam.delete_role(RoleName="psysense-test-perm-check")
    print("  iam:DeleteRole = ALLOWED")
except Exception as e:
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
    if code == "AccessDenied":
        print(f"  iam:CreateRole = DENIED")
    else:
        print(f"  iam:CreateRole test error: {e}")

# 4. Test Cognito permission
print("\n=== COGNITO PERMISSION TEST ===")
try:
    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    cognito.list_user_pools(MaxResults=1)
    print("  cognito-idp:ListUserPools = ALLOWED")
except Exception as e:
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
    print(f"  cognito: {code or e}")

# 5. Test DynamoDB permission
print("\n=== DYNAMODB PERMISSION TEST ===")
try:
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.list_tables(Limit=1)
    print("  dynamodb:ListTables = ALLOWED")
except Exception as e:
    print(f"  dynamodb: {e}")

# 6. Test S3 permission
print("\n=== S3 PERMISSION TEST ===")
try:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.list_buckets()
    print("  s3:ListBuckets = ALLOWED")
except Exception as e:
    print(f"  s3: {e}")

print("\n=== SUMMARY ===")
print("If iam:CreateRole = ALLOWED, deployment will succeed.")
print("If iam:CreateRole = DENIED, deployment will fail on IAM role creation.")
