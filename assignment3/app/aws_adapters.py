import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError


class DynamoCallStore:
    def __init__(self, table_name: str | None = None) -> None:
        self.table_name = table_name or os.environ.get("CALLS_TABLE", "")

    def put_if_absent(self, event: dict[str, Any]) -> bool:
        if not self.table_name:
            raise RuntimeError("CALLS_TABLE is not configured")
        table = boto3.resource(
            "dynamodb", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        ).Table(self.table_name)
        try:
            table.put_item(
                Item={
                    "event_id": event["event_id"],
                    "account_id": event["account_id"],
                    "disposition": event["disposition"],
                    "attempt": event["attempt"],
                    "completed_at": event["completed_at"],
                },
                ConditionExpression="attribute_not_exists(event_id)",
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise


class SqsRetryQueue:
    def __init__(self, queue_url: str | None = None) -> None:
        self.queue_url = queue_url or os.environ.get("RETRY_QUEUE_URL", "")

    def enqueue(self, message: dict[str, Any]) -> None:
        if not self.queue_url:
            raise RuntimeError("RETRY_QUEUE_URL is not configured")
        client = boto3.client(
            "sqs", region_name=os.environ.get("AWS_REGION", "ap-south-1")
        )
        client.send_message(
            QueueUrl=self.queue_url,
            MessageBody=json.dumps(message),
            MessageGroupId=message["account_id"],
            MessageDeduplicationId=message["event_id"],
        )