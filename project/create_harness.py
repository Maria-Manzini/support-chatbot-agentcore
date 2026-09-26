import boto3

REGION = "us-east-1"
MODEL_ID = "us.amazon.nova-pro-v1:0"
HARNESS_NAME = "support-chatbot-harness"


def build_system_prompt():
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read()
    with open("online_shop_faq.md", "r", encoding="utf-8") as f:
        faq = f.read()
    return prompt.replace("{{FAQ}}", faq)


def main():
    system_prompt = build_system_prompt()
    client = boto3.client("bedrock-agentcore-control", region_name=REGION)

    try:
        response = client.create_agent_runtime(
            agentRuntimeName=HARNESS_NAME,
            description="Customer support chatbot harness",
            foundationModel=MODEL_ID,
            systemPrompt=system_prompt,
        )
        runtime_id = response["agentRuntimeId"]
        print(f"Created harness: {runtime_id}")
    except client.exceptions.ConflictException:
        runtimes = client.list_agent_runtimes()["agentRuntimes"]
        runtime_id = next(r["agentRuntimeId"] for r in runtimes if r["name"] == HARNESS_NAME)
        client.update_agent_runtime(
            agentRuntimeId=runtime_id,
            foundationModel=MODEL_ID,
            systemPrompt=system_prompt,
        )
        print(f"Updated existing harness: {runtime_id}")

    print(f"agentRuntimeId={runtime_id}")


if __name__ == "__main__":
    main()