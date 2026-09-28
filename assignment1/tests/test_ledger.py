from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from ledger import LoanNotFoundError, collection_efficiency, init_db, load_loans_csv, post_payment


def make_db(tmp_path, loan_id="loan-1", outstanding="100.00", emi="50.00"):
    conn = init_db(tmp_path / "ledger.sqlite")
    conn.execute(
        "INSERT INTO loans VALUES (?, ?, ?, ?, ?)",
        (loan_id, "borrower-1", int(Decimal(emi) * 100), "2026-09-10", int(Decimal(outstanding) * 100)),
    )
    return conn


def test_happy_path_posts_payment_and_reduces_balance(tmp_path):
    conn = make_db(tmp_path)

    assert post_payment(conn, "loan-1", "25.50", "txn-1") == "POSTED"
    assert conn.execute("SELECT outstanding_paise FROM loans").fetchone()[0] == 7450
    assert tuple(conn.execute("SELECT applied_paise, excess_paise FROM payments").fetchone()) == (2550, 0)
    conn.close()


def test_duplicate_transaction_is_not_applied_twice(tmp_path):
    conn = make_db(tmp_path)

    assert post_payment(conn, "loan-1", "25.00", "txn-1") == "POSTED"
    assert post_payment(conn, "loan-1", "25.00", "txn-1") == "DUPLICATE"
    assert conn.execute("SELECT outstanding_paise FROM loans").fetchone()[0] == 7500
    assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
    conn.close()


def test_overpayment_records_excess_and_caps_outstanding_at_zero(tmp_path):
    conn = make_db(tmp_path, outstanding="30.00")

    assert post_payment(conn, "loan-1", "45.00", "txn-1") == "OVERPAID"
    assert conn.execute("SELECT outstanding_paise FROM loans").fetchone()[0] == 0
    assert tuple(conn.execute("SELECT amount_paise, applied_paise, excess_paise FROM payments").fetchone()) == (4500, 3000, 1500)
    conn.close()


@pytest.mark.parametrize("amount", ["0", "-1", "1.001", "NaN"])
def test_rejects_invalid_amount(amount, tmp_path):
    conn = make_db(tmp_path)

    with pytest.raises(ValueError):
        post_payment(conn, "loan-1", amount, "txn-1")
    assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0
    conn.close()


def test_unknown_loan_is_rejected_without_recording_payment(tmp_path):
    conn = make_db(tmp_path)

    with pytest.raises(LoanNotFoundError, match="unknown loan_id"):
        post_payment(conn, "missing", "1.00", "txn-1")
    assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0
    conn.close()


def test_eight_threads_posting_same_transaction_only_apply_once(tmp_path):
    db_path = tmp_path / "ledger.sqlite"
    setup = init_db(db_path)
    setup.execute(
        "INSERT INTO loans VALUES (?, ?, ?, ?, ?)",
        ("loan-1", "borrower-1", 10000, "2026-09-10", 10000),
    )
    setup.close()

    def post_from_independent_connection(_):
        conn = init_db(db_path)
        try:
            return post_payment(conn, "loan-1", "10.00", "same-txn")
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(post_from_independent_connection, range(8)))

    assert results.count("POSTED") == 1
    assert results.count("DUPLICATE") == 7
    verify = init_db(db_path)
    assert verify.execute("SELECT outstanding_paise FROM loans").fetchone()[0] == 9000
    assert verify.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
    verify.close()


def test_collection_efficiency_and_zero_denominator(tmp_path):
    conn = make_db(tmp_path, emi="50.00")
    assert post_payment(conn, "loan-1", "25.00", "txn-1") == "POSTED"
    assert collection_efficiency(conn, 2026, 9) == 0.5
    assert collection_efficiency(conn, 2026, 8) == 0.0
    conn.close()


def test_csv_loader_reports_invalid_and_duplicate_rows(tmp_path):
    conn = init_db(tmp_path / "ledger.sqlite")
    csv_path = tmp_path / "loans.csv"
    csv_path.write_text(
        "loan_id,borrower_id,emi_amount,due_date,outstanding_amount\n"
        "loan-1,b-1,50.00,2026-09-10,100.00\n"
        "loan-2,b-2,10.00,not-a-date,20.00\n"
        "loan-1,b-3,20.00,2026-09-11,30.00\n",
        encoding="utf-8",
    )

    rejected = load_loans_csv(conn, csv_path)

    assert [row["row"] for row in rejected] == [3, 4]
    assert "due_date" in rejected[0]["reason"]
    assert conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 1
    conn.close()