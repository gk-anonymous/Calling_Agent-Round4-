from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import create_app
from app.retry import schedule_retry


IST = ZoneInfo("Asia/Kolkata")


class MemoryStore:
    def __init__(self):
        self.events = set()

    def put_if_absent(self, event):
        event_id = event["event_id"]
        if event_id in self.events:
            return False
        self.events.add(event_id)
        return True


class MemoryQueue:
    def __init__(self):
        self.messages = {}

    def enqueue(self, message):
        self.messages.setdefault(message["event_id"], message)


def test_schedule_retry_at_0730_ist_moves_to_0800():
    now = datetime(2026, 9, 25, 7, 30, tzinfo=IST)

    assert schedule_retry("account-1", 0, now) == datetime(2026, 9, 25, 8, 0, tzinfo=IST)


def test_schedule_retry_at_1845_ist_moves_to_next_day():
    now = datetime(2026, 9, 25, 18, 45, tzinfo=IST)

    assert schedule_retry("account-1", 0, now) == datetime(2026, 9, 26, 8, 0, tzinfo=IST)


def test_schedule_retry_at_2300_ist_moves_to_next_day():
    now = datetime(2026, 9, 25, 23, 0, tzinfo=IST)

    assert schedule_retry("account-1", 0, now) == datetime(2026, 9, 26, 8, 0, tzinfo=IST)


def test_third_retry_is_not_scheduled():
    assert schedule_retry("account-1", 3, datetime(2026, 9, 25, 10, tzinfo=IST)) is None


def test_webhook_is_idempotent_and_queues_retry_once():
    store = MemoryStore()
    queue = MemoryQueue()
    client = TestClient(create_app(store, queue))
    payload = {
        "event_id": "cc234578-b508-4f6e-9d07-41617dcd2545",
        "account_id": "account-1",
        "disposition": "NO_ANSWER",
        "attempt": 0,
        "completed_at": "2026-09-25T07:30:00+05:30",
    }

    first = client.post("/webhook/call-completed", json=payload)
    second = client.post("/webhook/call-completed", json=payload)

    assert first.status_code == 202
    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    assert len(queue.messages) == 1
    assert next(iter(queue.messages.values()))["next_call"] == "2026-09-25T02:30:00+00:00"


def test_validation_rejects_missing_timezone_and_health_is_live():
    client = TestClient(create_app(MemoryStore(), MemoryQueue()))

    assert client.get("/health").json() == {"status": "ok"}
    response = client.post(
        "/webhook/call-completed",
        json={
            "event_id": "cc234578-b508-4f6e-9d07-41617dcd2545",
            "account_id": "account-1",
            "disposition": "BUSY",
            "attempt": 0,
            "completed_at": "2026-09-25T07:30:00",
        },
    )
    assert response.status_code == 422