import csv
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class LoanNotFoundError(LookupError):
    pass


def init_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS loans (
            loan_id TEXT PRIMARY KEY,
            borrower_id TEXT NOT NULL,
            emi_paise INTEGER NOT NULL CHECK (emi_paise >= 0),
            due_date TEXT NOT NULL CHECK (date(due_date) IS NOT NULL),
            outstanding_paise INTEGER NOT NULL CHECK (outstanding_paise >= 0)
        );

        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY,
            loan_id TEXT NOT NULL REFERENCES loans(loan_id),
            amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
            applied_paise INTEGER NOT NULL CHECK (applied_paise >= 0),
            excess_paise INTEGER NOT NULL CHECK (excess_paise >= 0),
            paid_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            gateway_txn_id TEXT NOT NULL UNIQUE,
            CHECK (applied_paise + excess_paise = amount_paise)
        );

        CREATE INDEX IF NOT EXISTS idx_loans_due_date
            ON loans(due_date);
        CREATE INDEX IF NOT EXISTS idx_payments_paid_at
            ON payments(paid_at);
        """
    )
    return conn


def _to_paise(value: Any, field_name: str) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a valid monetary amount") from exc

    if not amount.is_finite():
        raise ValueError(f"{field_name} must be finite")

    paise = amount * 100
    if paise != paise.to_integral_value():
        raise ValueError(f"{field_name} must have at most two decimal places")

    return int(paise)


def post_payment(
    conn: sqlite3.Connection,
    loan_id: str,
    amount: Any,
    gateway_txn_id: str,
) -> str:
    amount_paise = _to_paise(amount, "amount")
    if amount_paise <= 0:
        raise ValueError("amount must be greater than zero")
    if not isinstance(gateway_txn_id, str) or not gateway_txn_id.strip():
        raise ValueError("gateway_txn_id must be a non-empty string")

    conn.execute("BEGIN IMMEDIATE")
    try:
        duplicate = conn.execute(
            "SELECT 1 FROM payments WHERE gateway_txn_id = ?",
            (gateway_txn_id,),
        ).fetchone()
        if duplicate:
            conn.commit()
            return "DUPLICATE"

        loan = conn.execute(
            "SELECT outstanding_paise FROM loans WHERE loan_id = ?", (loan_id,)
        ).fetchone()
        if loan is None:
            raise LoanNotFoundError(f"unknown loan_id: {loan_id}")

        outstanding = loan["outstanding_paise"]
        applied = min(amount_paise, outstanding)
        excess = amount_paise - applied
        conn.execute(
            """INSERT INTO payments
               (loan_id, amount_paise, applied_paise, excess_paise, gateway_txn_id)
               VALUES (?, ?, ?, ?, ?)""",
            (loan_id, amount_paise, applied, excess, gateway_txn_id),
        )
        conn.execute(
            "UPDATE loans SET outstanding_paise = ? WHERE loan_id = ?",
            (outstanding - applied, loan_id),
        )
        conn.commit()
        return "OVERPAID" if excess else "POSTED"
    except Exception:
        conn.rollback()
        raise


def collection_efficiency(
    conn: sqlite3.Connection, year: int, month: int
) -> float:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    try:
        month_start = date(year, month, 1)
    except ValueError as exc:
        raise ValueError("year must be a valid calendar year") from exc
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)

    emi_due = conn.execute(
        """SELECT COALESCE(SUM(emi_paise), 0)
           FROM loans WHERE due_date >= ? AND due_date < ?""",
        (month_start.isoformat(), next_month.isoformat()),
    ).fetchone()[0]
    collected = conn.execute(
        """SELECT COALESCE(SUM(amount_paise), 0)
           FROM payments
           WHERE date(paid_at) >= ? AND date(paid_at) < ?""",
        (month_start.isoformat(), next_month.isoformat()),
    ).fetchone()[0]
    if emi_due == 0:
        return 0.0
    return float(Decimal(collected) / Decimal(emi_due))


def load_loans_csv(conn: sqlite3.Connection, path: str | Path) -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    with open(path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        required = {"loan_id", "borrower_id", "emi_amount", "due_date", "outstanding_amount"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or []))
            raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

        for row in reader:
            line_number = reader.line_num
            try:
                loan_id = row["loan_id"].strip()
                borrower_id = row["borrower_id"].strip()
                if not loan_id or not borrower_id:
                    raise ValueError("loan_id and borrower_id are required")
                try:
                    parsed_due_date = date.fromisoformat(row["due_date"].strip())
                except ValueError as exc:
                    raise ValueError("due_date must use YYYY-MM-DD") from exc

                emi_paise = _to_paise(row["emi_amount"], "emi_amount")
                outstanding_paise = _to_paise(row["outstanding_amount"], "outstanding_amount")
                if emi_paise < 0 or outstanding_paise < 0:
                    raise ValueError("loan amounts cannot be negative")

                conn.execute("SAVEPOINT load_loan_row")
                conn.execute(
                    """INSERT INTO loans
                       (loan_id, borrower_id, emi_paise, due_date, outstanding_paise)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        loan_id,
                        borrower_id,
                        emi_paise,
                        parsed_due_date.isoformat(),
                        outstanding_paise,
                    ),
                )
                conn.execute("RELEASE load_loan_row")
            except (ValueError, sqlite3.IntegrityError) as exc:
                if conn.in_transaction:
                    try:
                        conn.execute("ROLLBACK TO load_loan_row")
                        conn.execute("RELEASE load_loan_row")
                    except sqlite3.OperationalError:
                        pass
                rejected.append(
                    {"row": line_number, "loan_id": row.get("loan_id", ""), "reason": str(exc)}
                )

    conn.commit()
    return rejected