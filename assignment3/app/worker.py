import json
import logging
import os
import time
from typing import Any

import boto3
import httpx


logger = logging.getLogger("crm_retry_worker")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def process_message(message: dict[str, Any], client: httpx.Client, crm_url: str) -> None:
    response = client.post(crm_url, json=message)
    response.raise_for_status()


def run() -> None:
    region = os.environ.get("AWS_REGION", "ap-south-1")
    queue_url = os.environ["RETRY_QUEUE_URL"]
    crm_url = os.environ["CRM_URL"]
    crm_token = os.environ["CRM_BEARER_TOKEN"]
    sqs = boto3.client("sqs", region_name=region)

    with httpx.Client(
        timeout=httpx.Timeout(10.0),
        headers={"Authorization": f"Bearer {crm_token}"},
    ) as client:
        while True:
            batch = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
                VisibilityTimeout=60,
            ).get("Messages", [])
            for item in batch:
                body = json.loads(item["Body"])
                try:
                    process_message(body, client, crm_url)
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=item["ReceiptHandle"],
                    )
                    logger.info(
                        json.dumps(
                            {"event": "crm_retry_delivered", "event_id": body["event_id"]},
                            separators=(",", ":"),
                        )
                    )
                except (httpx.HTTPError, ValueError, KeyError):
                    logger.exception(
                        json.dumps(
                            {"event": "crm_retry_failed", "event_id": body.get("event_id")},
                            separators=(",", ":"),
                        )
                    )
                    time.sleep(1)


if __name__ == "__main__":
    run()