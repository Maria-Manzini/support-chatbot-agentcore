import uuid
import boto3

REGION = "us-east-1"
HARNESS_NAME = "support-chatbot-harness"


def get_runtime_id(client):
    runtimes = client.list_agent_runtimes()["items"]
    return next(r["agentRuntimeId"] for r in runtimes if r["name"] == HARNESS_NAME)


def main():
    control_client = boto3.client("bedrock-agentcore-control", region_name=REGION)
    runtime_client = boto3.client("bedrock-agentcore", region_name=REGION)

    runtime_id = get_runtime_id(control_client)
    session_id = str(uuid.uuid4())

    print("Support chatbot ready. Type 'quit' to exit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        response = runtime_client.invoke_agent_runtime(
            agentRuntimeId=runtime_id,
            sessionId=session_id,
            inputText=user_input,
        )

        completion = response.get("outputText") or response.get("completion") or str(response)
        print(f"Assistant: {completion}\n")


if __name__ == "__main__":
    main()