import boto3

cf = boto3.client("cloudformation", region_name="us-east-1")

# Delete the failed stack first
try:
    cf.delete_stack(StackName="psysense-dev")
    print("Cleaning up failed stack...")
    import time
    for _ in range(20):
        time.sleep(3)
        try:
            cf.describe_stacks(StackName="psysense-dev")
        except:
            print("Stack cleaned.")
            break
except:
    pass

# Check for registered hooks/type configurations
print("\n--- Checking CloudFormation Hooks ---")
try:
    types = cf.list_types(
        Visibility="PRIVATE",
        Type="HOOK",
    )
    for t in types.get("TypeSummaries", []):
        print("Hook:", t.get("TypeName"), "Status:", t.get("DefaultVersionId"))
except Exception as e:
    print("Cannot list hooks:", e)

# Try with PUBLIC too
try:
    types = cf.list_types(
        Visibility="PUBLIC",
        Type="HOOK",
        Filters={"Category": "ACTIVATED"},
    )
    for t in types.get("TypeSummaries", []):
        print("Public Hook:", t.get("TypeName"))
except Exception as e:
    print("Cannot list public hooks:", e)

# Check type configurations
print("\n--- Checking Hook Configurations ---")
try:
    config = cf.batch_describe_type_configurations(
        TypeConfigurationIdentifiers=[
            {
                "Type": "HOOK",
                "TypeName": "AWS::EarlyValidation::PropertyValidation",
            }
        ]
    )
    for tc in config.get("TypeConfigurations", []):
        print("Config:", tc.get("Configuration"))
    for err in config.get("Errors", []):
        print("Error:", err.get("ErrorCode"), err.get("ErrorMessage"))
except Exception as e:
    print("Config check error:", e)
