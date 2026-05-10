import boto3
iam = boto3.client("iam", region_name="us-east-1")
try:
    policies = iam.list_attached_user_policies(UserName="hitan")
    for p in policies["AttachedPolicies"]:
        print("Attached:", p["PolicyName"], p["PolicyArn"])
    groups = iam.list_groups_for_user(UserName="hitan")
    for g in groups["Groups"]:
        print("Group:", g["GroupName"])
        gp = iam.list_attached_group_policies(GroupName=g["GroupName"])
        for p in gp["AttachedPolicies"]:
            print("  ->", p["PolicyName"])
except Exception as e:
    print("Cannot check permissions:", e)
