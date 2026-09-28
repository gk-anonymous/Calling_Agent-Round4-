from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Disposition(str, Enum):
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    CONNECTED = "CONNECTED"
    PTP = "PTP"
    DISPUTE = "DISPUTE"
    WRONG_NUMBER = "WRONG_NUMBER"


class CallCompleted(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: UUID
    account_id: str = Field(min_length=1, max_length=128)
    disposition: Disposition
    attempt: int = Field(ge=0, le=3)
    completed_at: datetime

    @field_validator("completed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must include a timezone")
        return value