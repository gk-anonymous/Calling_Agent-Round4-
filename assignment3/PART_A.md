# Assignment 3 - Part A

## A1. Debugging findings

| Code area                                                  | Severity | Production issue                                                                                                            | Fix                                                                                                                     |
| ---------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `schedule_retry(..., history=[])`                          | Medium   | The mutable default list is shared across calls and `append` leaks state between requests.                                  | Remove `history` if unused, or default it to `None` and create a list per call.                                         |
| Retry limit check and `RETRY_GAPS_MIN[attempt]`            | High     | `attempt > len(...)` lets `attempt == 3` through, then indexes past the end. The attempt numbering is also undefined.       | Define `attempt` as the zero-based retry index and return `None` when it is outside `0..2`.                             |
| `datetime.now()`                                           | High     | Uses the host's local timezone, not necessarily India Standard Time.                                                        | Use timezone-aware `datetime.now(ZoneInfo("Asia/Kolkata"))`; reject naive supplied times.                               |
| `if next_time.hour > 19`                                   | High     | Misses exactly 19:00 and all times before 08:00. Replacing only the hour can also preserve invalid minutes.                 | Enforce the half-open local-time window `[08:00, 19:00)` and move out-of-window times to the next 08:00.                |
| `if disposition == "NO_ANSWER" or "BUSY"`                  | High     | Always true because the non-empty string `"BUSY"` is truthy. Every call result can schedule a retry.                        | Use `disposition in {"NO_ANSWER", "BUSY"}`.                                                                             |
| `body["account_id"]` and unvalidated `body.get(...)`       | Medium   | Missing fields or malformed types produce server errors or invalid scheduling values.                                       | Validate the payload with a Pydantic request model and return a client error for invalid data.                          |
| SQL assembled with an f-string                             | High     | `account_id` and `disposition` are untrusted input, enabling SQL injection.                                                 | Use parameterized SQL.                                                                                                  |
| Global `sqlite3.connect("calls.db")`                       | High     | Relative local storage is not shared/durable across ECS tasks; one global connection is a poor concurrent-request boundary. | Use a managed database or DynamoDB and a per-operation connection/session with explicit transaction handling.           |
| `DB.execute(...)` without commit/rollback                  | High     | The insert may remain uncommitted and be lost; failures can leave transaction state unclear.                                | Commit the insert transaction or use a transaction context that rolls back on errors.                                   |
| `async def` with synchronous SQLite and `requests.post`    | High     | Blocking I/O stalls the event loop and reduces throughput under load.                                                       | Use async I/O, or make the route synchronous; preferably queue CRM work instead of waiting in the webhook request.      |
| No event idempotency or webhook authentication             | High     | Duplicate or forged webhooks can create duplicate records/retries.                                                          | Verify the provider signature and apply a unique event ID/idempotency key in durable storage.                           |
| `CRM_URL = os.getenv("CRM_URL")`                           | Medium   | Missing configuration fails only when a request is made.                                                                    | Validate required configuration at startup and fail fast.                                                               |
| `requests.post(..., timeout=None)`                         | High     | A stalled CRM can hang a request indefinitely.                                                                              | Set bounded connect/read timeouts and decouple delivery with SQS.                                                       |
| `r.json()` without `raise_for_status()`                    | High     | HTTP 4xx/5xx responses may be treated as success.                                                                           | Call `raise_for_status()` and retry only transient failures.                                                            |
| `except:` and fixed one-second retry                       | Medium   | Hides programming errors, has no backoff/jitter, and can amplify a CRM outage.                                              | Catch expected network errors, log safely, use exponential backoff, and send exhausted messages to a dead-letter queue. |
| Passing `nxt` directly to `json=`                          | High     | `datetime` is not JSON serializable by the default encoder.                                                                 | Convert it to an ISO-8601 string, such as `nxt.isoformat()`.                                                            |
| CRM is notified even when `nxt is None`                    | Medium   | The final exhausted attempt can send a meaningless `next_call: null`.                                                       | Notify only when a retry time exists.                                                                                   |
| `notify_crm` swallows final failures; handler returns `ok` | High     | The caller is told the webhook succeeded even if work was lost; failures are invisible.                                     | Persist first, queue durably, return an accurate accepted response, and monitor delivery failures.                      |
| No table initialization shown                              | Medium   | A fresh deployment fails if the `calls` table does not exist.                                                               | Create/manage schema in migrations or infrastructure, not implicitly at import time.                                    |
| No PII/log retention or access controls shown              | High     | Account/phone data can be exposed or retained beyond policy.                                                                | Keep PII in approved India-region services, encrypt it, restrict access, redact logs, and set retention.                |

### Corrected retry function

Assumption: `attempt` is the zero-based retry index: `0` uses 30 minutes, `1` uses 120, and `2` uses 240. Values `3` and above mean no retries remain.

```python
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
CALL_START = time(8, 0)
CALL_END = time(19, 0)
RETRY_GAPS_MIN = (30, 120, 240)

def schedule_retry(account_id, attempt, now=None):
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
        next_time = next_time.replace(
            hour=8, minute=0, second=0, microsecond=0
        )
    elif next_time.time() >= CALL_END:
        next_day = next_time.date() + timedelta(days=1)
        next_time = datetime.combine(next_day, CALL_START, tzinfo=IST)

    return next_time
```

### Corrected handler condition

```python
if disposition in {"NO_ANSWER", "BUSY"}:
    nxt = schedule_retry(account_id, attempt)
    if nxt is not None:
        notify_crm(account_id, nxt.isoformat())
```

For production, the handler should enqueue the retry rather than synchronously call the CRM from an async request.

## A2. AWS short answers

### 1. Production architecture in `ap-south-1`

```text
Voice platform
    |
    v
AWS WAF (rate limits / common web exploits)
    |
    v
Public ALB (HTTPS, ACM certificate)
    |
    v
ECS Fargate API tasks in private subnets (multi-AZ, autoscaled)
    |                         |
    |                         +--> DynamoDB in ap-south-1
    |                              event ID idempotency, KMS encryption,
    |                              point-in-time recovery
    v
SQS FIFO retry queue + DLQ (regional, encrypted)
    |
    v
ECS Fargate CRM worker in private subnets
    |
    +--> CRM over HTTPS (CRM and data handling must also meet India residency)

Secrets Manager + KMS --> task secret / encryption
CloudWatch Logs, metrics, alarms --> redact PII
ECR --> container image
```

Keep the ALB public and application tasks/data services private. Use at least two Availability Zones; autoscale the API by ALB requests per target and the worker by queue depth. Keep PII, backups, logs, queue, keys, and databases in `ap-south-1`; confirm the CRM itself processes/stores PII in India too.

### 2. ECS roles and secret access

The **task execution role** is used by ECS to pull ECR images, write logs, and inject configured secrets. The **task role** is assumed by application code when it calls AWS APIs. If the app fetches one secret at runtime, grant this statement to the task role; if ECS injects it at startup, grant it to the execution role:

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:ap-south-1:123456789012:secret:crm-token-AbCdEf"
}
```

If using a customer-managed KMS key, also grant `kms:Decrypt` on that specific key only.

### 3. ALB 5xx after deploy

1. Check CloudWatch `HTTPCode_ELB_5XX` versus `HTTPCode_Target_5XX` to locate whether the load balancer or app is failing.
2. Check target health, ECS deployment events, stopped-task reasons, container health checks, and CloudWatch logs; compare the failing release's configuration/secrets with the previous one.
3. Stop or roll back the deployment: let the ECS deployment circuit breaker revert, or update the service to the last known-good task definition.
4. Confirm healthy targets and that 5xx rates return to baseline before redeploying a fix.

### 4. Lambda + API Gateway vs ECS Fargate

Choose **Lambda + API Gateway** for short, stateless, bursty webhook traffic where scale-to-zero is valuable. Choose **ECS Fargate** for sustained high throughput, long-running processes, or a continuously running SQS worker. For a 500-request/second peak plus CRM retry processing, Fargate is a reasonable fit.
