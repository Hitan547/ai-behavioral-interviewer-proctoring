import boto3, json

iam = boto3.client("iam", region_name="us-east-1")

# Check a few broad Lambda roles for permissions
candidates = [
    "DigitranVA-Lambda-Role",
    "FarmerPlatformLambdaRole", 
    "microgpt-saas-lambda-role",
    "industrial-panel-lambda-role",
]

for role_name in candidates:
    print(f"\n=== {role_name} ===")
    try:
        role = iam.get_role(RoleName=role_name)
        arn = role["Role"]["Arn"]
        print(f"  ARN: {arn}")
        
        # Attached managed policies
        policies = iam.list_attached_role_policies(RoleName=role_name)
        for p in policies["AttachedPolicies"]:
            print(f"  Managed Policy: {p['PolicyName']} ({p['PolicyArn']})")
        
        # Inline policies
        inline = iam.list_role_policies(RoleName=role_name)
        for pname in inline["PolicyNames"]:
            print(f"  Inline Policy: {pname}")
            try:
                doc = iam.get_role_policy(RoleName=role_name, PolicyName=pname)
                actions = []
                for stmt in doc["PolicyDocument"].get("Statement", []):
                    a = stmt.get("Action", [])
                    if isinstance(a, str):
                        a = [a]
                    actions.extend(a)
                print(f"    Actions: {', '.join(actions[:15])}")
            except:
                pass
    except Exception as e:
        print(f"  Error: {e}")
