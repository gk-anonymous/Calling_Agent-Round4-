## A1. Merge promise windows

```python
def merge_windows(windows: list[list[int]]) -> list[list[int]]:
    if not windows:
        return []

    ordered = sorted(windows, key=lambda window: window[0])
    merged = [ordered[0][:]]

    for start, end in ordered[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return merged
```

## A2. Excess call attempts

````python
def flag_excess_attempts(
    attempts: list[tuple[str, int]], limit: int = 3, window: int = 3600
) -> set[str]:
    if limit <= 0:
        return {borrower_id for borrower_id, _ in attempts}

    ordered = sorted(attempts)
    flagged = set()
    left = 0

    for right, (borrower_id, timestamp) in enumerate(ordered):
        while left <= right and (
            ordered[left][0] != borrower_id
            or timestamp - ordered[left][1] >= window
        ):
            left += 1

        if right - left + 1 >= limit:
            flagged.add(borrower_id)

    return flagged


## A3. SQL

### 1. Outstanding by DPD bucket

```sql
SELECT
    CASE
        WHEN CURRENT_DATE - due_date <= 0 THEN 'Current'
        WHEN CURRENT_DATE - due_date <= 30 THEN '1-30'
        WHEN CURRENT_DATE - due_date <= 60 THEN '31-60'
        WHEN CURRENT_DATE - due_date <= 90 THEN '61-90'
        ELSE '91+'
    END AS dpd_bucket,
    COUNT(*) AS loan_count,
    SUM(outstanding_amount) AS total_outstanding
FROM loans
WHERE outstanding_amount > 0
GROUP BY 1
ORDER BY MIN(CURRENT_DATE - due_date);
````

The brief's `61-90` and `90+` labels overlap at day 90; this uses `91+` to
make the buckets mutually exclusive.

### 2. Overdue loans without a qualifying recent call

```sql
SELECT l.*
FROM loans AS l
WHERE l.outstanding_amount > 0
  AND l.due_date < CURRENT_DATE
  AND NOT EXISTS (
      SELECT 1
      FROM call_logs AS c
      WHERE c.loan_id = l.loan_id
        AND c.called_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
        AND c.disposition IN ('CONNECTED', 'PTP', 'DISPUTE')
  );
```

### 3. Latest payment and time since the previous payment

```sql
WITH payment_history AS (
    SELECT
        l.borrower_id,
        p.payment_id,
        p.amount,
        p.paid_at,
        LAG(p.paid_at) OVER (
            PARTITION BY l.borrower_id
            ORDER BY p.paid_at, p.payment_id
        ) AS previous_paid_at,
        ROW_NUMBER() OVER (
            PARTITION BY l.borrower_id
            ORDER BY p.paid_at DESC, p.payment_id DESC
        ) AS newest
    FROM payments AS p
    JOIN loans AS l ON l.loan_id = p.loan_id
)
SELECT
    b.borrower_id,
    h.amount AS latest_payment_amount,
    h.paid_at AS latest_paid_at,
    h.paid_at - h.previous_paid_at AS gap_since_previous
FROM borrowers AS b
LEFT JOIN payment_history AS h
  ON h.borrower_id = b.borrower_id AND h.newest = 1;
```

### 4. Duplicate webhook and indexes

Without database-enforced idempotency, two concurrent deliveries can both
observe the old balance, insert a payment, and reduce the balance twice. Put a
`UNIQUE` constraint on `payments(gateway_txn_id)` and post the payment insert
and balance update in one transaction. In PostgreSQL, lock the loan row with
`SELECT ... FOR UPDATE`; treat a unique-key conflict as a duplicate and do not
apply the balance update.
