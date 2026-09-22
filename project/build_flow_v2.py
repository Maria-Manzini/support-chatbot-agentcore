import boto3
import json


# ============================================================
# CONFIGURATION
# ============================================================

REGION = "us-east-1"
MODEL_ID = "us.amazon.nova-pro-v1:0"
FLOW_ID = "62BUP68GDL"

FLOW_NAME = "support-chatbot-flow-api"


# ============================================================
# AWS CLIENTS
# ============================================================

bedrock_agent = boto3.client(
    "bedrock-agent",
    region_name=REGION,
)

lambda_client = boto3.client(
    "lambda",
    region_name=REGION,
)


# ============================================================
# PROMPTS
# ============================================================

CLASSIFIER_PROMPT = """You are a routing classifier for a customer support chatbot.

Read the customer's message and classify it into exactly ONE category.

Respond with ONLY one word:
BUG_REPORT
FAQ
OTHER

BUG_REPORT:
The customer describes a malfunction, error, crash, broken feature, or something not working as expected on the platform.

FAQ:
The customer asks about orders, shipping, tracking, returns, refunds, payments, promotions, products, account/password, or privacy.

OTHER:
Anything else, including unrelated requests or platform questions the FAQ likely doesn't cover.

Customer message: {{input}}

Respond with only one word: BUG_REPORT, FAQ, or OTHER.
"""


BUG_REPORT_PROMPT = """You are collecting a bug report from a customer.

Extract or ask for these three fields:

- description
- stepsToReproduce
- environment

If any are missing, ask only for what's missing, one question at a time.

Once all three are present, output them as JSON:

{"description": "...", "stepsToReproduce": "...", "environment": "..."}

Customer message: {{input}}
"""


FAQ_FILE = "online_shop_faq.md"

with open(FAQ_FILE, "r", encoding="utf-8") as f:
    faq_content = f.read()


FAQ_PROMPT = f"""You are a customer support assistant.

Answer the customer's question using ONLY the FAQ below.

Do not use outside knowledge or invent policies, prices, or timeframes not in the FAQ.

If the FAQ doesn't contain enough information, say you'll connect them with human support instead of guessing.

FAQ:
{faq_content}

Customer question: {{{{input}}}}
"""


HANDOFF_PROMPT = """Politely explain that a human support agent can help with this.

Direct the customer to use the help/contact form on the site or reply to any order email with their order number.

Mention support is available Monday-Friday (excluding holidays) and typically responds within 1-2 business days.

Do not invent a phone number.

Customer message: {{input}}
"""


# ============================================================
# NODE HELPERS
# ============================================================

def prompt_node(name, prompt_text):
    """
    Creates a Bedrock Prompt node.

    Every prompt has an input named exactly 'input'.
    """

    return {
        "name": name,
        "type": "Prompt",

        "configuration": {
            "prompt": {
                "sourceConfiguration": {
                    "inline": {
                        "modelId": MODEL_ID,
                        "templateType": "TEXT",

                        "inferenceConfiguration": {
                            "text": {
                                "temperature": 0,
                                "topP": 1,
                                "maxTokens": 500,
                            }
                        },

                        "templateConfiguration": {
                            "text": {
                                "text": prompt_text
                            }
                        },
                    }
                }
            }
        },

        "inputs": [
            {
                "name": "input",
                "type": "String",
                "expression": "$.data",
            }
        ],

        "outputs": [
            {
                "name": "modelCompletion",
                "type": "String",
            }
        ],
    }


def output_node(name):
    """
    Creates a Bedrock Output node.

    The input MUST be named 'document'.
    """

    return {
        "name": name,
        "type": "Output",

        "inputs": [
            {
                "name": "document",
                "type": "String",
                "expression": "$.data",
            }
        ],
    }


# ============================================================
# AWS RESOURCE HELPERS
# ============================================================

def get_lambda_arn():
    """
    Gets the ARN for the create-bug-report Lambda function.
    """

    response = lambda_client.get_function(
        FunctionName="create-bug-report"
    )

    arn = response["Configuration"]["FunctionArn"]

    print(f"Found Lambda:")
    print(f"  {arn}")

    return arn


# ============================================================
# BUILD FLOW DEFINITION
# ============================================================

def build_definition(lambda_arn):

    # --------------------------------------------------------
    # INPUT NODE
    # --------------------------------------------------------

    flow_input = {
        "name": "FlowInputNode",
        "type": "Input",

        "outputs": [
            {
                "name": "document",
                "type": "String",
            }
        ],
    }


    # --------------------------------------------------------
    # CLASSIFIER
    # --------------------------------------------------------

    classifier = prompt_node(
        "ClassifierPrompt",
        CLASSIFIER_PROMPT,
    )


    # --------------------------------------------------------
    # ROUTING CONDITION
    # --------------------------------------------------------

    route_condition = {
        "name": "RouteCondition",
        "type": "Condition",

        "inputs": [
            {
                "name": "classification",
                "type": "String",
                "expression": "$.data",
            }
        ],

        "configuration": {
            "condition": {
                "conditions": [

                    {
                        "name": "BugReport",
                        "expression": 'classification == "BUG_REPORT"',
                    },

                    {
                        "name": "FAQ",
                        "expression": 'classification == "FAQ"',
                    },

                    {
                        "name": "default",
                    },
                ]
            }
        },
    }


    # --------------------------------------------------------
    # BUG REPORT PROMPT
    # --------------------------------------------------------

    bug_report_prompt = prompt_node(
        "BugReportPrompt",
        BUG_REPORT_PROMPT,
    )


    # --------------------------------------------------------
    # BUG REPORT LAMBDA
    # --------------------------------------------------------

    bug_report_lambda = {
        "name": "CreateBugReportLambda",
        "type": "LambdaFunction",

        "configuration": {
            "lambdaFunction": {
                "lambdaArn": lambda_arn,
            }
        },

        "inputs": [
            {
                "name": "input",
                "type": "String",
                "expression": "$.data",
            }
        ],

        "outputs": [
            {
                "name": "functionResponse",
                "type": "String",
            }
        ],
    }


    # --------------------------------------------------------
    # FAQ PROMPT
    # --------------------------------------------------------

    faq_prompt = prompt_node(
        "FAQPrompt",
        FAQ_PROMPT,
    )


    # --------------------------------------------------------
    # HANDOFF PROMPT
    # --------------------------------------------------------

    handoff_prompt = prompt_node(
        "HandoffPrompt",
        HANDOFF_PROMPT,
    )


    # --------------------------------------------------------
    # OUTPUT NODES
    #
    # IMPORTANT:
    # Each Output node has exactly one required input:
    # 'document'
    # --------------------------------------------------------

    bug_report_output = output_node(
        "BugReportOutputNode"
    )

    faq_output = output_node(
        "FAQOutputNode"
    )

    handoff_output = output_node(
        "HandoffOutputNode"
    )


    # --------------------------------------------------------
    # ALL NODES
    # --------------------------------------------------------

    nodes = [
        flow_input,
        classifier,
        route_condition,
        bug_report_prompt,
        bug_report_lambda,
        faq_prompt,
        handoff_prompt,
        bug_report_output,
        faq_output,
        handoff_output,
    ]


    # ========================================================
    # CONNECTIONS
    # ========================================================

    connections = [

        # ----------------------------------------------------
        # INPUT -> CLASSIFIER
        # ----------------------------------------------------

        {
            "name": "InputToClassifier",
            "type": "Data",
            "source": "FlowInputNode",
            "target": "ClassifierPrompt",

            "configuration": {
                "data": {
                    "sourceOutput": "document",
                    "targetInput": "input",
                }
            },
        },


        # ----------------------------------------------------
        # INPUT -> BUG REPORT PROMPT
        #
        # Provides BugReportPrompt.input.
        # RouteCondition determines whether this branch runs.
        # ----------------------------------------------------

        {
            "name": "InputToBugReport",
            "type": "Data",
            "source": "FlowInputNode",
            "target": "BugReportPrompt",

            "configuration": {
                "data": {
                    "sourceOutput": "document",
                    "targetInput": "input",
                }
            },
        },


        # ----------------------------------------------------
        # INPUT -> FAQ PROMPT
        #
        # Provides FAQPrompt.input.
        # ----------------------------------------------------

        {
            "name": "InputToFAQ",
            "type": "Data",
            "source": "FlowInputNode",
            "target": "FAQPrompt",

            "configuration": {
                "data": {
                    "sourceOutput": "document",
                    "targetInput": "input",
                }
            },
        },


        # ----------------------------------------------------
        # INPUT -> HANDOFF PROMPT
        #
        # Provides HandoffPrompt.input.
        # ----------------------------------------------------

        {
            "name": "InputToHandoff",
            "type": "Data",
            "source": "FlowInputNode",
            "target": "HandoffPrompt",

            "configuration": {
                "data": {
                    "sourceOutput": "document",
                    "targetInput": "input",
                }
            },
        },


        # ----------------------------------------------------
        # CLASSIFIER -> ROUTE CONDITION
        # ----------------------------------------------------

        {
            "name": "ClassifierToCondition",
            "type": "Data",
            "source": "ClassifierPrompt",
            "target": "RouteCondition",

            "configuration": {
                "data": {
                    "sourceOutput": "modelCompletion",
                    "targetInput": "classification",
                }
            },
        },


        # ----------------------------------------------------
        # ROUTE -> BUG REPORT
        # ----------------------------------------------------

        {
            "name": "ConditionToBugReport",
            "type": "Conditional",
            "source": "RouteCondition",
            "target": "BugReportPrompt",

            "configuration": {
                "conditional": {
                    "condition": "BugReport",
                }
            },
        },


        # ----------------------------------------------------
        # ROUTE -> FAQ
        # ----------------------------------------------------

        {
            "name": "ConditionToFAQ",
            "type": "Conditional",
            "source": "RouteCondition",
            "target": "FAQPrompt",

            "configuration": {
                "conditional": {
                    "condition": "FAQ",
                }
            },
        },


        # ----------------------------------------------------
        # ROUTE -> HANDOFF
        # ----------------------------------------------------

        {
            "name": "ConditionToHandoff",
            "type": "Conditional",
            "source": "RouteCondition",
            "target": "HandoffPrompt",

            "configuration": {
                "conditional": {
                    "condition": "default",
                }
            },
        },


        # ----------------------------------------------------
        # BUG REPORT PROMPT -> LAMBDA
        # ----------------------------------------------------

        {
            "name": "BugReportToLambda",
            "type": "Data",
            "source": "BugReportPrompt",
            "target": "CreateBugReportLambda",

            "configuration": {
                "data": {
                    "sourceOutput": "modelCompletion",
                    "targetInput": "input",
                }
            },
        },


        # ----------------------------------------------------
        # LAMBDA -> BUG REPORT OUTPUT
        # ----------------------------------------------------

        {
            "name": "LambdaToBugReportOutput",
            "type": "Data",
            "source": "CreateBugReportLambda",
            "target": "BugReportOutputNode",

            "configuration": {
                "data": {
                    "sourceOutput": "functionResponse",
                    "targetInput": "document",
                }
            },
        },


        # ----------------------------------------------------
        # FAQ -> FAQ OUTPUT
        # ----------------------------------------------------

        {
            "name": "FAQToOutput",
            "type": "Data",
            "source": "FAQPrompt",
            "target": "FAQOutputNode",

            "configuration": {
                "data": {
                    "sourceOutput": "modelCompletion",
                    "targetInput": "document",
                }
            },
        },


        # ----------------------------------------------------
        # HANDOFF -> HANDOFF OUTPUT
        # ----------------------------------------------------

        {
            "name": "HandoffToOutput",
            "type": "Data",
            "source": "HandoffPrompt",
            "target": "HandoffOutputNode",

            "configuration": {
                "data": {
                    "sourceOutput": "modelCompletion",
                    "targetInput": "document",
                }
            },
        },
    ]


    return {
        "nodes": nodes,
        "connections": connections,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("Amazon Bedrock Support Chatbot Flow Updater")
    print("=" * 60)

    print(f"\nRegion:  {REGION}")
    print(f"Flow ID: {FLOW_ID}")

    # --------------------------------------------------------
    # Get Lambda ARN
    # --------------------------------------------------------

    print("\nGetting Lambda ARN...")

    lambda_arn = get_lambda_arn()


    # --------------------------------------------------------
    # Build definition
    # --------------------------------------------------------

    print("\nBuilding flow definition...")

    definition = build_definition(
        lambda_arn
    )

    print(
        f"Created {len(definition['nodes'])} nodes "
        f"and {len(definition['connections'])} connections."
    )


    # --------------------------------------------------------
    # Ask for execution role
    # --------------------------------------------------------

    print("\nYour Bedrock Flow execution role is required.")

    role_arn = input(
        "Paste your Flow's execution role ARN: "
    ).strip()

    if not role_arn:
        raise ValueError(
            "Execution role ARN cannot be empty."
        )


    # --------------------------------------------------------
    # Update flow
    # --------------------------------------------------------

    print("\nUpdating flow...")

    try:

        response = bedrock_agent.update_flow(

            flowIdentifier=FLOW_ID,

            name=FLOW_NAME,

            description=(
                "Customer support chatbot flow "
                "created via API"
            ),

            executionRoleArn=role_arn,

            definition=definition,
        )

        print("\nFlow update response:")

        print(
            json.dumps(
                response,
                indent=2,
                default=str,
            )
        )

    except Exception as e:

        print("\nERROR while updating flow:")
        print(str(e))

        raise


    # --------------------------------------------------------
    # Prepare flow
    # --------------------------------------------------------

    print("\nPreparing flow...")

    try:

        prepare_response = (
            bedrock_agent.prepare_flow(
                flowIdentifier=FLOW_ID
            )
        )

        print("\nPrepare response:")

        print(
            json.dumps(
                prepare_response,
                indent=2,
                default=str,
            )
        )

    except Exception as e:

        print("\nERROR while preparing flow:")
        print(str(e))

        raise


    # --------------------------------------------------------
    # Done
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

    print(f"\nFlow ID: {FLOW_ID}")

    print(
        "\nThe flow was updated and prepare_flow() was called."
    )

    print(
        "\nIf preparation succeeds, check the Bedrock console "
        "and create a version/alias."
    )

    print(
        "\nThe IAM policy warning about deleted nodes is "
        "separate from the flow validation."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()