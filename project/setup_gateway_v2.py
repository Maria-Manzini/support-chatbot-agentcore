import boto3
import time

REGION = "us-east-1"
GATEWAY_NAME = "bug-report-gateway"
TARGET_NAME = "bugreports"
FUNCTION_NAME = "create_bug_report"
LAMBDA_FUNCTION_NAME = "create-bug-report"
ROLE_NAME = "AmazonBedrockAgentCoreGatewayRole_SupportChatbot"

iam = boto3.client("iam", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
gateway_client = boto3.client("bedrock-agentcore-control", region_name=REGION)


def get_lambda_arn():
    resp = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
    return resp["Configuration"]["FunctionArn"]


def get_or_create_gateway_role():
    trust_policy = (
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
        '"Principal":{"Service":"bedrock-agentcore.amazonaws.com"},'
        '"Action":"sts:AssumeRole"}]}'
    )
    try:
        resp = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=trust_policy,
            Description="Execution role for the bug-report AgentCore Gateway",
        )
        role_arn = resp["Role"]["Arn"]
        iam.put_role_policy(
            RoleName=ROLE_NAME,
            PolicyName="InvokeLambda",
            PolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["lambda:InvokeFunction"],"Resource":"*"}]}',
        )
        print(f"Created gateway role: {role_arn}")
        time.sleep(10)
        return role_arn
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        print(f"Reusing existing gateway role: {role_arn}")
        return role_arn


def main():
    lambda_arn = get_lambda_arn()
    print(f"Found Lambda ARN: {lambda_arn}")

    role_arn = get_or_create_gateway_role()

    try:
        gateway = gateway_client.create_gateway(
            name=GATEWAY_NAME,
            description="Gateway exposing the bug report creation tool",
            protocolType="MCP",
            roleArn=role_arn,
            authorizerType="AWS_IAM",
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
        "inputSchema": {
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
        gatewayIdentifier=gateway_id,
        name=TARGET_NAME,
                credentialProviderConfigurations=[
            {"credentialProviderType": "GATEWAY_IAM_ROLE"}
        ],
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

    gateway_details = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
    print(f"gatewayArn={gateway_details.get('gatewayArn', 'N/A')}")


if __name__ == "__main__":
    main()