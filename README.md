# Customer Support Chatbot — Amazon Bedrock Flow

An AI customer-support chatbot for an online shop, built on Amazon Bedrock Flows with prompt-based routing into three behaviours.

**Region:** `us-east-1`
**Model:** `us.amazon.nova-pro-v1:0` (Amazon Nova Pro)
**Flow ID:** `62BUP68GDL` (`support-chatbot-flow-api`)

---

## What it does

Every customer message is classified into exactly one of three routes by a classifier prompt node, then branched by a condition node:

1. **Bug report** — collects `description`, `stepsToReproduce`, and `environment`, then invokes the `create-bug-report` Lambda, which writes a ticket to DynamoDB and returns a `ticketId`.
2. **Platform FAQ** — answers using only the embedded FAQ content. No outside knowledge, no invented policies or timeframes.
3. **Human hand-off** — anything out of scope, or any FAQ question the FAQ doesn't cover, is redirected to human support (contact form or order-email reply, Mon–Fri, 1–2 business day response). No phone number is invented.

---

## Architecture

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

Flow input fans out to all four prompt nodes, since each destination prompt needs the original customer message. The condition node only decides which branch actually executes.

### Nodes

| Node | Type | Purpose |
|---|---|---|
| `FlowInputNode` | Input | Receives the customer message |
| `ClassifierPrompt` | Prompt | Returns exactly one of `BUG_REPORT` / `FAQ` / `OTHER` |
| `RouteCondition` | Condition | Branches on the classifier output |
| `BugReportPrompt` | Prompt | Collects/extracts the three required bug fields as JSON |
| `CreateBugReportLambda` | Lambda | Writes the ticket to DynamoDB, returns `ticketId` |
| `FAQPrompt` | Prompt | Answers from the embedded FAQ only |
| `HandoffPrompt` | Prompt | Human support redirect |
| `BugReportOutputNode` / `FAQOutputNode` / `HandoffOutputNode` | Output | One output node per branch |

---

## Repository contents

| File | Purpose |
|---|---|
| `build_flow_v2.py` | Builds/updates the entire Bedrock Flow via the API |
| `system_prompt.txt` | Original AgentCore-style system prompt (three-route policy, injection defence) |
| `online_shop_faq.md` | FAQ source content embedded into the FAQ prompt node |
| `create_bug_report.py` | Lambda handler — writes tickets to DynamoDB |
| `cloudformation_tool.yaml` | Lambda + DynamoDB + IAM role |
| `cloudformation_testing.yaml` | S3 bucket for evaluation artefacts |
| `harness-tests.json` | 9-case test suite (all three routes + edge cases) |
| `flow_tests_template.json` | Template for the evaluation dataset generator |
| `generate_eval_dataset.py` | Produces evaluation JSONL from the template |
| `chat.py`, `create_harness.py`, `setup_gateway.py` | AgentCore-based scripts from the original architecture |

---

## Deployment

```bash
# 1. Deploy Lambda + DynamoDB
aws cloudformation deploy \
  --template-file cloudformation_tool.yaml \
  --stack-name bug-report-tool-stack \
  --capabilities CAPABILITY_IAM \
  --region us-east-1

# 2. Upload the real Lambda code (the template ships a placeholder)
python3 -c "import zipfile; zipfile.ZipFile('function.zip','w').write('create_bug_report.py')"
aws lambda update-function-code \
  --function-name create-bug-report \
  --zip-file fileb://function.zip \
  --region us-east-1

# 3. Build / update the flow
python build_flow_v2.py
```

Then open the flow in the console, click **Save** to validate, and use the **Test flow** panel.

---

## Current status

**Working:**
- CloudFormation stack deployed (Lambda + DynamoDB table `bug-report-tool-stack-bug-reports`)
- Real Lambda code uploaded and active
- Flow created and reaching **Prepared** status with all nodes and connections valid
- Amazon Nova Pro confirmed working via the Bedrock Playground

**Outstanding:**
- Flow execution returns `Access denied when calling InvokeModel` at the `ClassifierPrompt` node, despite an explicit `bedrock:InvokeModel` allow policy on the flow's execution role and confirmed model availability in the same account. Under investigation — see Challenge 8 below.
- Evaluation job not yet run (blocked behind the above).

---

## Challenges encountered

Documented honestly, because several cost significant time and some remain unresolved.

### 1. Architecture mismatch between instructions and rubric
The written project instructions specified an AgentCore managed harness with routing performed entirely by a single system prompt, and explicitly said *not* to use classifier nodes or conditional flow nodes. The submission feedback then required screenshots of a classifier prompt configuration, condition node expressions, and an FAQ prompt node template — i.e. a Bedrock **Flow**. The build was started against the first spec and had to be redirected to the second. `system_prompt.txt` and the AgentCore scripts in this repo are artefacts of the original approach.

### 2. Terminal paste disabled
The workspace terminal did not accept `Ctrl+V` or right-click paste, so every command had to be retyped by hand for a long stretch. This directly caused at least one failed install (`-- break system packages` instead of `--break-system-packages`). **Resolved:** `Shift+Insert` works.

### 3. Local environment couldn't substitute
Attempted to move to a local VS Code install to work around the paste problem, but the local machine had no AWS CLI. A silent `msiexec /qn` install did not complete (likely blocked without admin rights), and the school network's firewall blocked the AWS console entirely. Reverted to the workspace.

### 4. Expiring credentials
The AWS Academy account issues temporary `ASIA...` credentials that expire within hours, requiring reconfiguration at the start of every session. `aws configure` prompts for only the access key and secret — it does **not** prompt for the session token, which these credentials also require. Missing it produces a misleading `InvalidClientTokenId` error. The token must be set separately:

```bash
aws configure set aws_session_token <token>
```

### 5. Missing standard tooling
The `zip` utility is not installed in the workspace, so the Lambda deployment package had to be built with Python's `zipfile` module instead.

### 6. Console lost unsaved work
A full seven-node flow built through the console UI was lost despite saving during the build. This is what motivated the switch to building the flow via the boto3 API instead, which turned out to be far more reliable and reproducible — the flow definition is now version-controlled in `build_flow_v2.py` rather than existing only as console state.

### 7. Undocumented flow schema requirements
The Bedrock Flow API rejects several intuitive-looking definitions. Discovered only through iterative validation errors:

- Prompt nodes **must** name their output exactly `modelCompletion`. Custom names like `classification` are rejected.
- Lambda nodes **must** name their output exactly `functionResponse`.
- Output nodes **must** have an input named exactly `document`.
- An output node input accepts only **one** incoming connection. Routing three branches into a single output node fails validation. **Resolved** by giving each branch its own output node (`BugReportOutputNode`, `FAQOutputNode`, `HandoffOutputNode`).

### 8. `InvokeModel` access denied at runtime (unresolved)
The flow prepares successfully but fails at execution with `Access denied when calling InvokeModel`. Verified so far:

- The flow's execution role is `AmazonBedrockExecutionRoleForFlows_2GO5B0VIEJ8` (confirmed via `get-flow`).
- An inline policy `AllowInvokeNovaPro` granting `bedrock:InvokeModel` is attached to that role (confirmed via `list-role-policies`).
- Nova Pro invokes successfully from the Bedrock Playground under the same account, so the model itself is enabled.

Remaining hypotheses: `us.amazon.nova-pro-v1:0` is a cross-region inference profile, which requires permissions on both the inference-profile ARN and the underlying foundation-model ARNs in every region it routes to; or a Service Control Policy on the training account restricts what `Resource: "*"` actually resolves to.

### 9. Git remote pointed at the upstream template
The workspace repo's `origin` was Udacity's own template repository, so pushes returned `403 Permission denied`. Resolved by repointing origin to a personal repository. Git identity (`user.name` / `user.email`) also has to be reset each time the workspace container is recycled.

### 10. Dependency version mismatch
`requirements.txt` originally pinned `boto3==1.42.54`, while AgentCore requires 1.43+. Updated to `boto3>=1.43.0`.

---

## Testing

`harness-tests.json` contains nine cases covering all three routes plus edge cases: incomplete bug report, complete bug report in a single message, an FAQ question the FAQ doesn't cover, an out-of-scope request, and a prompt-injection attempt. Each `expected` value is written as a behavioural description suitable for LLM-as-a-judge evaluation rather than exact string matching.

Each automated test runs in a fresh single-turn session, so no test expectation depends on the outcome of a previous one.

## Cleanup

```bash
aws cloudformation delete-stack --stack-name bug-report-tool-stack --region us-east-1
aws cloudformation delete-stack --stack-name bug-report-testing-stack --region us-east-1
```

Flows are deleted from the Bedrock console, or via `aws bedrock-agent delete-flow --flow-identifier 62BUP68GDL`.
