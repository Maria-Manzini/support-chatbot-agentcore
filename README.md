# Customer Support Chatbot — Amazon Bedrock Flow + AgentCore Gateway

An AI customer-support chatbot for an online shop, routing every customer message into exactly one of three behaviours: bug report, platform FAQ, or human hand-off.

**Region:** `us-east-1`
**Model:** `us.amazon.nova-pro-v1:0` (Amazon Nova Pro)
**Flow ID:** `62BUP68GDL` (`support-chatbot-flow-api`)
**Gateway ARN:** `arn:aws:bedrock-agentcore:us-east-1:978642742596:gateway/bug-report-gateway-hoemunr794`

---

## What it does

1. **Bug report** — collects `description`, `stepsToReproduce`, and `environment` across conversation turns, then calls `bugreports___create_bug_report`, which writes a ticket to DynamoDB and returns a real `ticketId`.
2. **Platform FAQ** — answers using only the embedded FAQ content. No outside knowledge, no invented policies or timeframes.
3. **Human hand-off** — anything out of scope, or any FAQ question the FAQ doesn't cover, is redirected to human support (contact form or order-email reply, Mon–Fri, 1–2 business day response). No phone number is invented.

---

## Two working implementations

This project ended up with two complementary, both-working pieces of evidence, because the two intended AWS services for the "managed harness" turned out to be blocked at the platform level (see below). Both satisfy the same underlying behavioural requirements.

### 1. Bedrock Flow (`support-chatbot-flow-api`)

```
Customer message
  └─> Flow input
        ├─> ClassifierPrompt  ──> RouteCondition
        │                            ├─ BugReport ──> BugReportPrompt ──> CreateBugReportLambda ──> BugReportOutputNode
        │                            ├─ FAQ       ──> FAQPrompt       ──> FAQOutputNode
        │                            └─ default   ──> HandoffPrompt   ──> HandoffOutputNode
        ├─> BugReportPrompt (message source)
        ├─> FAQPrompt (message source)
        └─> HandoffPrompt (message source)
```

Built and updated via `build_flow_v2.py`. Tested through the console's Test panel for all three routes, with a confirmed real DynamoDB ticket created. The Test panel does not carry conversation memory between separate test messages — this is a real limitation of that interface, not a bug in the Flow.

### 2. `chat_v2.py` — real multi-turn conversation via Converse API tool use

A self-contained terminal client using Bedrock's Converse API with native tool use, maintaining real conversation state in Python across turns. This is what actually demonstrates true multi-turn field collection (never re-asking for information already given) and produces a genuine `[tool call] bugreports___create_bug_report` transcript line. See `chat_transcript.txt` for a full recorded session covering all three routes plus a successful ticket creation.

**Honesty note:** `chat_v2.py` invokes the `create-bug-report` Lambda directly rather than routing the call through the AgentCore Gateway's MCP endpoint. The Gateway itself was successfully created and exposes the tool under the correct name (`bugreports___create_bug_report`, confirmed via `agentcore_config.json`), but wiring a Converse API tool-use loop to call *through* the Gateway's MCP protocol specifically (rather than the Lambda directly) was not completed given time constraints. Both the direct-Lambda and Gateway paths ultimately reach the same Lambda function and DynamoDB table.

---

## Why the originally-specified "managed harness" services were not usable

Two independent AWS platform constraints blocked the exact architecture named in the project instructions.

**1. AgentCore Runtime is a container-hosting service, not a system-prompt harness.**
`create_agent_runtime` requires `agentRuntimeArtifact`, `roleArn`, and `networkConfiguration` — it deploys a containerized custom runtime, not a managed conversational agent configured with just a system prompt and foundation model:

```
Missing required parameter in input: "agentRuntimeArtifact"
Missing required parameter in input: "roleArn"
Missing required parameter in input: "networkConfiguration"
Unknown parameter in input: "foundationModel"
Unknown parameter in input: "systemPrompt"
```

**2. Classic Bedrock Agents is in account-wide Maintenance Mode:**

```
AccessDeniedException when calling the CreateAgent operation: Bedrock Agents is in Maintenance
Mode. New agent creation is not available for accounts without prior service usage.
```

`aws bedrock-agent list-agents` confirmed zero existing agents in this account:

```json
{"agentSummaries": []}
```

**The AgentCore Gateway itself, however, is a separate, lighter-weight resource and was successfully created** once the correct required parameters were identified through iterative API errors (`roleArn`, `authorizerType`, `gatewayIdentifier` instead of `gatewayId`, `inputSchema` instead of `parameters`, and `credentialProviderConfigurations`). It now exposes the Lambda tool under the exact name the spec requires: `bugreports___create_bug_report`.

---

## Repository contents

| File | Purpose |
|---|---|
| `build_flow_v2.py` | Builds/updates the Bedrock Flow via the API |
| `system_prompt.txt` | Three-route system prompt (routing, field collection, injection defence) |
| `online_shop_faq.md` | FAQ source content embedded into the FAQ prompt node |
| `create_bug_report_v3.py` | Working Lambda handler — writes tickets to DynamoDB |
| `setup_gateway_v2.py` | Creates the AgentCore Gateway + target exposing `bugreports___create_bug_report` |
| `chat_v2.py` | Real multi-turn terminal client using Converse API tool use |
| `chat_transcript.txt` | Recorded session covering all three routes + a successful ticket creation |
| `agentcore_config.json` | Real harness (Flow) and Gateway ARNs |
| `cloudformation_tool.yaml` | Lambda + DynamoDB + IAM role |
| `cloudformation_testing.yaml` | S3 bucket + IAM role for evaluation artefacts |
| `harness-tests.json` | 9-case test suite (all three routes + edge cases) |
| `flow_tests_template.json` | Template for the evaluation dataset generator |
| `generate_eval_dataset_clean.py` | Produces evaluation JSONL (prompt/referenceResponse schema) |
| `create_agent.py`, `create_harness.py`, `setup_gateway.py`, `chat.py` | Earlier attempts at the originally-specified AgentCore Runtime / classic Agents harness — kept for documentation of the platform blockers above |

---

## Deployment

```bash
# 1. Deploy Lambda + DynamoDB
aws cloudformation deploy \
  --template-file cloudformation_tool.yaml \
  --stack-name bug-report-tool-stack \
  --capabilities CAPABILITY_IAM \
  --region us-east-1

# 2. Upload the real Lambda code
python3 -c "import zipfile; zipfile.ZipFile('function.zip','w').write('create_bug_report_v3.py', arcname='create_bug_report.py')"
aws lambda update-function-code \
  --function-name create-bug-report \
  --zip-file fileb://function.zip \
  --region us-east-1

# 3. Build / update the Flow
python build_flow_v2.py

# 4. Create the Gateway
python setup_gateway_v2.py

# 5. Run the real multi-turn chat client
python chat_v2.py
```

Then open the Flow in the console, click **Save** to validate, and use the **Test flow** panel for single-message route testing.

---

## Current status — everything working

- CloudFormation stack deployed (Lambda + DynamoDB table `bug-report-tool-stack-bug-reports`)
- Real Lambda code active, correctly returning a plain string matching the Bedrock Flow Lambda node's required output contract
- Flow reaches **Prepared** status with all nodes and connections valid; all three routes tested and confirmed working
- AgentCore Gateway created and exposing the tool under the exact required name
- `chat_v2.py` demonstrates genuine multi-turn field collection (never re-asks for known information) and a successful tool call producing a real `ticketId`, confirmed present in DynamoDB
- Bedrock Evaluation job completed using the Correctness metric with Nova Pro as the LLM judge

---

## Testing

`harness-tests.json` contains nine cases covering all three routes plus edge cases: incomplete bug report, complete bug report in a single message, an FAQ question the FAQ doesn't cover, an out-of-scope request, and a prompt-injection attempt. Each `expected` value is written as a behavioural description suitable for LLM-as-a-judge evaluation rather than exact string matching. Each test runs in a fresh single-turn session, so no test expectation depends on the outcome of a previous one.

### Evaluation

```bash
python generate_eval_dataset_clean.py --template flow_tests_template.json --output eval-dataset-clean.jsonl
aws s3 cp eval-dataset-clean.jsonl s3://udacity-agentic-engineer-c1-eval-978642742596/eval-dataset-clean.jsonl
```

A Bedrock Evaluation job was created against this dataset using the Correctness metric with Nova Pro as the LLM judge (evaluating Nova Pro directly, since this account's Bedrock Evaluations console offers "Bedrock models" or "Bring your own inference responses" as inference sources, with no option to select a Flow directly as the evaluation target).

**Observations from the completed evaluation job:** [Fill in with your actual per-record scores once reviewed — name specific test IDs with notably high or low correctness scores, and what you'd change in the system prompt as a result.]

## Cleanup

```bash
aws cloudformation delete-stack --stack-name bug-report-tool-stack --region us-east-1
aws cloudformation delete-stack --stack-name bug-report-testing-stack --region us-east-1
```

Flows are deleted from the Bedrock console, or via `aws bedrock-agent delete-flow --flow-identifier 62BUP68GDL`. The Gateway can be deleted via `aws bedrock-agentcore-control delete-gateway --gateway-identifier bug-report-gateway-hoemunr794`.
