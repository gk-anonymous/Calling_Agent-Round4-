import json
import logging
from datetime import timezone
from typing import Any, Protocol

from fastapi import FastAPI

from app.aws_adapters import DynamoCallStore, SqsRetryQueue
from app.models import CallCompleted, Disposition
from app.retry import schedule_retry


logger = logging.getLogger("call_webhook")
logging.basicConfig(level=logging.INFO, format="%(message)s")


class CallStore(Protocol):
    def put_if_absent(self, event: dict[str, Any]) -> bool: ...


class RetryQueue(Protocol):
    def enqueue(self, message: dict[str, Any]) -> None: ...


def create_app(store: CallStore | None = None, retry_queue: RetryQueue | None = None) -> FastAPI:
    call_store = store or DynamoCallStore()
    queue = retry_queue or SqsRetryQueue()
    application = FastAPI(title="Predixion Call Webhook", version="1.0.0")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/webhook/call-completed", status_code=202)
    def call_completed(event: CallCompleted) -> dict[str, str | None]:
        event_data = event.model_dump(mode="json")
        inserted = call_store.put_if_absent(event_data)
        next_call = None

        if event.disposition in {Disposition.NO_ANSWER, Disposition.BUSY}:
            retry_at = schedule_retry(
                event.account_id,
                event.attempt,
                event.completed_at,
            )
            if retry_at is not None:
                next_call = retry_at.astimezone(timezone.utc).isoformat()
                queue.enqueue(
                    {
                        "event_id": str(event.event_id),
                        "account_id": event.account_id,
                        "attempt": event.attempt + 1,
                        "next_call": next_call,
                    }
                )

        result = "accepted" if inserted else "duplicate"
        logger.info(
            json.dumps(
                {
                    "event": "call_webhook_processed",
                    "event_id": str(event.event_id),
                    "status": result,
                    "disposition": event.disposition.value,
                    "retry_scheduled": next_call is not None,
                },
                separators=(",", ":"),
            )
        )
        return {"status": result, "next_call": next_call}

    return application


app = create_app()