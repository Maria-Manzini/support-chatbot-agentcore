"""
Interactive terminal chatbot using Amazon Bedrock's Converse API with native
tool use. Maintains real conversation state across turns in Python (a
messages list), so bug-report field collection genuinely persists between
turns -- unlike a stateless single-shot Flow test.

This sidesteps two confirmed platform blockers in this account:
  - AgentCore Runtime requires a containerized artifact deployment
  - Classic Bedrock Agents is in account-wide Maintenance Mode

The Converse API's tool-use feature is a stable, well-documented Bedrock
capability and does not depend on either blocked service.

Usage: python chat.py
"""

import json
import boto3

REGION = "us-east-1"
MODEL_ID = "us.amazon.nova-pro-v1:0"
TOOL_NAME = "bugreports___create_bug_report"

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)


def build_system_prompt():
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read()
    with open("online_shop_faq.md", "r", encoding="utf-8") as f:
        faq = f.read()
    return prompt.replace("{{FAQ}}", faq)


TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": TOOL_NAME,
                "description": "Create a bug report ticket for a customer-reported platform issue.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "What is going wrong"},
                            "stepsToReproduce": {"type": "string", "description": "Steps that lead to the problem"},
                            "environment": {"type": "string", "description": "Browser/device/OS used"},
                        },
                        "required": ["description", "stepsToReproduce", "environment"],
                    }
                },
            }
        }
    ]
}


def invoke_bug_report_tool(tool_input):
    """Directly invokes the create-bug-report Lambda with the tool's arguments."""
    payload = {"input": json.dumps(tool_input)}
    response = lambda_client.invoke(
        FunctionName="create-bug-report",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    result_raw = response["Payload"].read().decode("utf-8")
    try:
        # Lambda may return a JSON string directly, or a JSON-encoded string of a string
        result = json.loads(result_raw)
        if isinstance(result, str):
            result = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        result = {"raw": result_raw}
    return result


def main():
    system_prompt = build_system_prompt()
    messages = []

    print("Support chatbot ready (Converse API + tool use). Type 'quit' to exit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": [{"text": user_input}]})

        while True:
            response = bedrock.converse(
                modelId=MODEL_ID,
                system=[{"text": system_prompt}],
                messages=messages,
                toolConfig=TOOL_CONFIG,
                inferenceConfig={"temperature": 0, "maxTokens": 500},
            )

            output_message = response["output"]["message"]
            messages.append(output_message)

            stop_reason = response.get("stopReason")

            if stop_reason == "tool_use":
                tool_results = []
                for block in output_message["content"]:
                    if "toolUse" in block:
                        tool_use = block["toolUse"]
                        print(f"[tool call] {TOOL_NAME} with input: {json.dumps(tool_use['input'])}")
                        result = invoke_bug_report_tool(tool_use["input"])
                        print(f"[tool result] {json.dumps(result)}")
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use["toolUseId"],
                                "content": [{"json": result}],
                            }
                        })
                messages.append({"role": "user", "content": tool_results})
                continue  # loop again so the model can respond to the tool result

            # Normal text response -- print it and break back out to wait for next user input
            for block in output_message["content"]:
                if "text" in block:
                    print(f"Assistant: {block['text']}\n")
            break


if __name__ == "__main__":
    main()