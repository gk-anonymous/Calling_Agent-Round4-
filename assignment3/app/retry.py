from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
CALL_START = time(8, 0)
CALL_END = time(19, 0)
RETRY_GAPS_MIN = (30, 120, 240)


def schedule_retry(
    account_id: str,
    attempt: int,
    now: datetime | None = None,
) -> datetime | None:
    """Return the next permitted retry time; attempt is the zero-based retry index."""
    if not account_id.strip():
        raise ValueError("account_id must not be empty")
    if attempt < 0:
        raise ValueError("attempt must be zero or greater")
    if attempt >= len(RETRY_GAPS_MIN):
        return None

    current = now or datetime.now(IST)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    current = current.astimezone(IST)
    next_time = current + timedelta(minutes=RETRY_GAPS_MIN[attempt])

    if next_time.time() < CALL_START:
        next_time = next_time.replace(hour=8, minute=0, second=0, microsecond=0)
    elif next_time.time() >= CALL_END:
        next_day = next_time.date() + timedelta(days=1)
        next_time = datetime.combine(next_day, CALL_START, tzinfo=IST)

    return next_time