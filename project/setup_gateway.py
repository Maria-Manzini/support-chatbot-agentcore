import boto3

REGION = "us-east-1"
GATEWAY_NAME = "bug-report-gateway"
TARGET_NAME = "bugreports"
FUNCTION_NAME = "create_bug_report"
LAMBDA_FUNCTION_NAME = "create-bug-report"


def get_lambda_arn(lambda_client):
    resp = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
    return resp["Configuration"]["FunctionArn"]


def main():
    lambda_client = boto3.client("lambda", region_name=REGION)
    gateway_client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    lambda_arn = get_lambda_arn(lambda_client)
    print(f"Found Lambda ARN: {lambda_arn}")

    try:
        gateway = gateway_client.create_gateway(
            name=GATEWAY_NAME,
            description="Gateway exposing the bug report creation tool",
            protocolType="MCP",
        )
        gateway_id = gateway["gatewayId"]
        print(f"Created gateway: {gateway_id}")
    except gateway_client.exceptions.ConflictException:
        gateways = gateway_client.list_gateways()["items"]
        gateway_id = next(g["gatewayId"] for g in gateways if g["name"] == GATEWAY_NAME)
        print(f"Reusing existing gateway: {gateway_id}")

    tool_schema = {
        "name": FUNCTION_NAME,
        "description": "Create a bug report ticket for a customer-reported platform issue.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What is going wrong"},
                "stepsToReproduce": {"type": "string", "description": "Steps that lead to the problem"},
                "environment": {"type": "string", "description": "Browser/device/OS used"},
            },
            "required": ["description", "stepsToReproduce", "environment"],
        },
    }

    gateway_client.create_gateway_target(
        gatewayId=gateway_id,
        name=TARGET_NAME,
        targetConfiguration={
            "mcp": {
                "lambda": {
                    "lambdaArn": lambda_arn,
                    "toolSchema": {"inlinePayload": [tool_schema]},
                }
            }
        },
    )

    print(f"Gateway target created. Tool exposed as: {TARGET_NAME}___{FUNCTION_NAME}")
    print(f"gatewayId={gateway_id}")


if __name__ == "__main__":
    main()