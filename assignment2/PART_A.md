# Assignment 2 - Part A

## A1. Capacity planning

Each account is attempted again only if the previous attempt did not connect. The probability that an account reaches attempt 1, 2, or 3 is therefore `1`, `0.75`, and `0.75^2`.

Expected attempts per account:

```text
1 + 0.75 + 0.75^2 = 2.3125 attempts
```

For any attempt, the expected line occupancy is:

```text
0.25 * 120 s + 0.75 * 30 s = 52.5 line-seconds
```

So expected line-seconds per account and for the whole campaign are:

```text
2.3125 * 52.5 = 121.40625 line-seconds/account
200,000 * 121.40625 = 24,281,250 line-seconds
```

A 10-hour calling day has `10 * 3,600 = 36,000` seconds. At perfect, even utilization, the average concurrent-line requirement is:

```text
24,281,250 / 36,000 = 674.48 lines
```

Round up: **675 concurrent lines is the mathematical minimum under these averages**. It assumes attempts are evenly spread across all ten hours and durations match their averages; it is not a robust operating target.

I would provision about **850 lines**, or roughly 26% above the minimum. Equivalently, this targets about 80% average utilization (`674.48 / 0.80 = 843.1`, rounded up). The headroom covers uneven arrival and answer patterns, duration variance, breaks or dialer pauses, carrier/setup overhead, and forecast error. I would refine the margin from observed peak-hour arrival rates and service-level goals; if completing every attempt within the day is a hard SLA, validate with a queueing/simulation model rather than relying only on average load.

## A2. A/B test

Treat each connected call as one independent observation, with PTP as a binary outcome. Let `pA` and `pB` be the PTP rates. Test whether B is higher using a one-sided two-proportion z-test at `alpha = 0.05`:

```text
H0: pB = pA
H1: pB > pA
```

Observed rates:

```text
pA = 880 / 4,000 = 0.22 (22%)
pB = 960 / 4,000 = 0.24 (24%)
difference = 0.24 - 0.22 = 0.02 (2 percentage points)
```

Under the null, the pooled estimate is:

```text
p_pool = (880 + 960) / (4,000 + 4,000) = 0.23
SE_null = sqrt(0.23 * 0.77 * (1/4,000 + 1/4,000)) = 0.00941
z = (0.24 - 0.22) / 0.00941 = 2.13
```

The one-sided p-value is approximately `0.017`, below `0.05`; reject the equal-rate null. B's PTP rate is significantly higher at the 95% confidence level. (The two-sided p-value is approximately `0.034`, also below `0.05`.)

However, PTP count is not the ultimate outcome. Kept PTPs are:

```text
A: 880 * 0.60 = 528 kept, or 528 / 4,000 = 13.2% of connected calls
B: 960 * 0.50 = 480 kept, or 480 / 4,000 = 12.0% of connected calls
```

**I would roll out A for now, not B.** B produces more promises, but fewer are kept: for equal-sized groups it yields 48 fewer on-time payments. A's kept-PTP rate is the more relevant business outcome. Confirm this downstream difference with a suitably powered test and compare collected amount, customer harm/complaints, and cost before making a permanent decision; the supplied PTP-rate test alone does not prove A is better on those outcomes.

## A3. Funnel diagnosis

Rates by stage (each stage divided by the immediately preceding stage):

| Week | Connected / dialed | RPC / connected | PTP / RPC | Paid / PTP | Paid / dialed |
| ---- | -----------------: | --------------: | --------: | ---------: | ------------: |
| W1   |              25.0% |           80.0% |     25.0% |      60.0% |         3.00% |
| W2   |              24.8% |           59.7% |     29.7% |      59.1% |         2.60% |
| W3   |              25.0% |           57.7% |     30.0% |      60.0% |         2.60% |

**The main break is between connected calls and RPC.** The connection rate stayed near 25%, and the RPC-to-PTP and PTP-to-paid conversion rates are broadly stable or improved. In contrast, RPC/connected fell from 80.0% in W1 to 59.7% in W2 and 57.7% in W3. The final paid-per-dial rate consequently fell from 3.00% to about 2.60%.

Hypotheses and first cuts to test:

1. **A worse phone/list mix is producing more non-borrower answers.** Cut connected calls and RPC rate by list/source, lender/state, phone number age/type, DPD bucket, and week; compare mix shifts as well as within-segment rates.
2. **A carrier, time-of-day, or routing change is connecting to the wrong person more often.** Cut by carrier/route, local call hour/day, campaign, and disposition; check whether the W2 change aligns with a routing or schedule change.
3. **RPC classification or agent behavior changed.** Audit a stratified sample of call recordings from W1 versus W2/W3, especially calls coded as non-RPC, and compare disposition rates by team/agent. This tests for mislabeling or a process change rather than a real contact-quality decline.

Start with the connected-call disposition breakdown by week and segment, then inspect recordings in the segments showing the largest deterioration. Keep the definition of “connected” and RPC consistent across weeks.

## A4. Scheduler design

Use each borrower's IANA timezone to evaluate the legal calling window. Store timestamps in UTC, but calculate local dates and the half-open local calling interval `[08:00, 19:00)` in the borrower's timezone. A callback time is a not-before time; if it falls outside the allowed window, schedule at the next legal window and do not call early.

Data structures:

- Account record keyed by `account_id`: timezone, DPD, outstanding amount, daily attempt count, last attempt timestamp, requested callback timestamp (if any), and a version number.
- `future`: min-heap keyed by each account's next legal eligible instant.
- `ready`: max-priority heap keyed by `-(DPD * outstanding_amount)`, with a stable tie-breaker. Heap entries include account ID and version so stale entries can be discarded lazily.
- In-flight set keyed by account ID, preventing a second line from dialing an account whose call is still active.

```text
function enqueue(account, now):
    if account is inactive or account.id is in_flight:
        return

    local_now = convert(now, account.timezone)
    local_day = date(local_now)
    attempts_today = attempts_for(account.id, local_day)

    if attempts_today >= 3:
        eligible = next_local_day_at_08(account.timezone, local_day)
    else:
        eligible = max(
            now,
            account.last_attempt_utc + 60 minutes, if a prior attempt exists,
            account.callback_utc, if a callback was requested
        )
        eligible = first_in_or_after_allowed_window(eligible, account.timezone)

    account.version += 1
    push(future, (eligible, account.id, account.version))

function on_line_free(now):
    while future is not empty and future.min.eligible <= now:
        entry = pop(future)
        account = accounts[entry.account_id]
        if entry.version != account.version or account.id in_flight:
            continue
        if account has become ineligible:
            enqueue(account, now)
            continue
        push(ready, (-(account.dpd * account.outstanding), stable_tie_breaker,
                     account.id, entry.version))

    while ready is not empty:
        entry = pop(ready)
        account = accounts[entry.account_id]
        if entry.version != account.version or account.id in_flight:
            continue
        if not is_legal_local_time(now, account.timezone):
            enqueue(account, now)
            continue
        if attempts_for(account.id, local_date(now, account.timezone)) >= 3:
            enqueue(account, now)
            continue
        if account.callback_utc exists and now < account.callback_utc:
            enqueue(account, now)
            continue
        mark account in_flight
        start_call(account.id)
        return

    if future is not empty:
        wait_until(future.min.eligible)
    else:
        wait_for_account_or_callback_update()

function on_call_finished(account_id, finished_at):
    remove account_id from in_flight
    record attempt using the local date at dial start
    update account.last_attempt_utc and any callback request
    enqueue(account, finished_at)
```

Before dialing, recheck eligibility atomically so parallel free lines cannot violate per-account limits. Reserve/increment the attempt for that local dial date at dial start, then reconcile the call result at completion. Account updates (new callback, payment, closure, priority change) increment the version and enqueue a replacement entry. A durable implementation should use a transactional reservation or compare-and-set across scheduler workers.

For `n` accounts, inserting/updating an account or selecting the next eligible account costs `O(log n)` heap work. Each entry is promoted at most once per eligibility cycle, also `O(log n)`; stale heap entries are discarded lazily. Storage is `O(n)` plus in-flight calls. Timezone/window calculation is constant work per scheduling decision.
