"""
Creates a classic Amazon Bedrock Agent as the 'managed harness', with an
action group ('bugreports') wired to the create-bug-report Lambda. This is
the correct service for a system-prompt-driven conversational agent with a
tool -- NOT AgentCore Runtime, which hosts containerized custom code.

Usage: python create_agent.py
"""

import time
import boto3

REGION = "us-east-1"
MODEL_ID = "amazon.nova-pro-v1:0"  # plain foundation model id for Agents (not the us. prefixed inference profile)
AGENT_NAME = "support-chatbot-agent"
ACTION_GROUP_NAME = "bugreports"

bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)


def build_system_prompt():
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read()
    with open("online_shop_faq.md", "r", encoding="utf-8") as f:
        faq = f.read()
    return prompt.replace("{{FAQ}}", faq)


def get_or_create_agent_role():
    role_name = "AmazonBedrockExecutionRoleForAgents_SupportChatbot"
    trust_policy = (
        '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",'
        '"Principal":{"Service":"bedrock.amazonaws.com"},'
        '"Action":"sts:AssumeRole"}]}'
    )
    try:
        resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy,
            Description="Execution role for the support chatbot Bedrock Agent",
        )
        role_arn = resp["Role"]["Arn"]
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="InvokeModelAndLambda",
            PolicyDocument='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":"*"},{"Effect":"Allow","Action":["lambda:InvokeFunction"],"Resource":"*"}]}',
        )
        print(f"Created role: {role_arn}")
        time.sleep(10)
        return role_arn
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
        print(f"Reusing existing role: {role_arn}")
        return role_arn


def get_lambda_arn():
    resp = lambda_client.get_function(FunctionName="create-bug-report")
    return resp["Configuration"]["FunctionArn"]


def main():
    role_arn = get_or_create_agent_role()
    lambda_arn = get_lambda_arn()
    system_prompt = build_system_prompt()

    existing = bedrock_agent.list_agents()["agentSummaries"]
    match = next((a for a in existing if a["agentName"] == AGENT_NAME), None)

    if match:
        agent_id = match["agentId"]
        print(f"Reusing existing agent: {agent_id}")
        bedrock_agent.update_agent(
            agentId=agent_id,
            agentName=AGENT_NAME,
            foundationModel=MODEL_ID,
            instruction=system_prompt,
            agentResourceRoleArn=role_arn,
        )
    else:
        resp = bedrock_agent.create_agent(
            agentName=AGENT_NAME,
            foundationModel=MODEL_ID,
            instruction=system_prompt,
            agentResourceRoleArn=role_arn,
            idleSessionTTLInSeconds=600,
        )
        agent_id = resp["agent"]["agentId"]
        print(f"Created agent: {agent_id}")

    time.sleep(5)

    try:
        lambda_client.add_permission(
            FunctionName="create-bug-report",
            StatementId="AllowBedrockAgentInvoke",
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
        )
    except lambda_client.exceptions.ResourceConflictException:
        pass

    function_schema = {
        "functions": [
            {
                "name": "create_bug_report",
                "description": "Create a bug report ticket for a customer-reported platform issue.",
                "parameters": {
                    "description": {"type": "string", "required": True, "description": "What is going wrong"},
                    "stepsToReproduce": {"type": "string", "required": True, "description": "Steps that lead to the problem"},
                    "environment": {"type": "string", "required": True, "description": "Browser/device/OS used"},
                },
            }
        ]
    }

    existing_groups = bedrock_agent.list_agent_action_groups(
        agentId=agent_id, agentVersion="DRAFT"
    )["actionGroupSummaries"]
    existing_group = next((g for g in existing_groups if g["actionGroupName"] == ACTION_GROUP_NAME), None)

    if existing_group:
        bedrock_agent.update_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupId=existing_group["actionGroupId"],
            actionGroupName=ACTION_GROUP_NAME,
            actionGroupExecutor={"lambda": lambda_arn},
            functionSchema=function_schema,
        )
        print("Updated existing action group.")
    else:
        bedrock_agent.create_agent_action_group(
            agentId=agent_id,
            agentVersion="DRAFT",
            actionGroupName=ACTION_GROUP_NAME,
            actionGroupExecutor={"lambda": lambda_arn},
            functionSchema=function_schema,
        )
        print("Created action group.")

    bedrock_agent.prepare_agent(agentId=agent_id)
    print("Agent preparing...")
    time.sleep(15)

    aliases = bedrock_agent.list_agent_aliases(agentId=agent_id)["agentAliasSummaries"]
    existing_alias = next((a for a in aliases if a["agentAliasName"] == "prod"), None)
    if existing_alias:
        alias_id = existing_alias["agentAliasId"]
        print(f"Reusing existing alias: {alias_id}")
    else:
        alias_resp = bedrock_agent.create_agent_alias(agentId=agent_id, agentAliasName="prod")
        alias_id = alias_resp["agentAlias"]["agentAliasId"]
        print(f"Created alias: {alias_id}")

    print("\n" + "=" * 50)
    print(f"agentId={agent_id}")
    print(f"agentAliasId={alias_id}")
    print("Save these two values -- chat.py and agentcore_config.json need them.")
    print("=" * 50)


if __name__ == "__main__":
    main()