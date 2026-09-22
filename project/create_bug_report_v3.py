import json
import os
import uuid
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "BugReports")
table = dynamodb.Table(TABLE_NAME)


def find_any_string(obj):
    """Dig through the event to find the first usable string value,
    regardless of exactly how Bedrock Flow structured it."""
    if isinstance(obj, str) and obj.strip():
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = find_any_string(v)
            if found:
                return found
    if isinstance(obj, list):
        for v in obj:
            found = find_any_string(v)
            if found:
                return found
    return None


def lambda_handler(event, context):
    print(f"DEBUG raw event: {json.dumps(event, default=str)}")
    try:
        raw_text = find_any_string(event) or ""

        # Try to parse it as the JSON BugReportPrompt was asked to produce
        description = steps_to_reproduce = environment = None
        try:
            fields = json.loads(raw_text)
            if isinstance(fields, dict):
                description = fields.get("description")
                steps_to_reproduce = fields.get("stepsToReproduce")
                environment = fields.get("environment")
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: if we couldn't parse structured fields, still create a
        # ticket using whatever raw text we found, so the pipeline never
        # silently fails to write to DynamoDB.
        if not description:
            description = raw_text or "No description captured"
        if not steps_to_reproduce:
            steps_to_reproduce = "Not explicitly parsed from input"
        if not environment:
            environment = "Not explicitly parsed from input"

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
        