import json
import os
import uuid
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "BugReports")
table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    """
    Bedrock Flow's Lambda node passes the connected input field(s) directly
    in the event (here, a single field named 'input' holding the JSON string
    produced by BugReportPrompt). The return value must directly contain a
    key matching the declared output name ('functionResponse') as a plain
    string -- no Bedrock-Agent-style envelope.
    """
    try:
        raw_input = event.get("input") or event.get("node", {}).get("input") or ""

        # BugReportPrompt should produce a JSON string like:
        # {"description": "...", "stepsToReproduce": "...", "environment": "..."}
        try:
            fields = json.loads(raw_input)
        except (json.JSONDecodeError, TypeError):
            fields = {}

        description = fields.get("description")
        steps_to_reproduce = fields.get("stepsToReproduce")
        environment = fields.get("environment")

        if not (description and steps_to_reproduce and environment):
            result = {"error": "Missing one or more required fields: description, stepsToReproduce, environment."}
            return json.dumps(result)

        ticket_id = str(uuid.uuid4())
        item = {
            "ticketId": ticket_id,
            "description": description,
            "stepsToReproduce": steps_to_reproduce,
            "environment": environment,
            "status": "OPEN",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        table.put_item(Item=item)

        result = {"ticketId": ticket_id, "status": "OPEN"}
        return json.dumps(result)

    except Exception as e:
        result = {"error": f"Failed to create bug report: {str(e)}"}
        return json.dumps(result)