import pandas as pd

from analytics import analyze_calls


def test_reports_rates_and_injected_state_batch_anomaly():
    accounts = pd.DataFrame(
        [
            {"account_id": "target", "state": "BR", "batch": "B7", "dpd": 10, "outstanding": 1000},
            {"account_id": "baseline", "state": "MH", "batch": "B1", "dpd": 45, "outstanding": 2000},
        ]
    )
    calls = pd.DataFrame(
        [
            {"account_id": "target", "called_at": "2026-08-03 10:00", "disposition": "WRONG_NUMBER", "days_to_promise": float("nan"), "ptp_kept": float("nan")},
            {"account_id": "target", "called_at": "2026-08-03 10:10", "disposition": "PTP", "days_to_promise": 3, "ptp_kept": 1.0},
            {"account_id": "baseline", "called_at": "2026-08-08 17:00", "disposition": "RPC_NO_PTP", "days_to_promise": float("nan"), "ptp_kept": float("nan")},
        ]
    )
    calls["called_at"] = pd.to_datetime(calls["called_at"])

    result = analyze_calls(accounts, calls)

    assert result["anomaly"]["target_attempts"] == 2
    assert result["anomaly"]["target_wrong_rate"] == 0.5
    assert result["weekpart"].set_index("day_type").loc["Weekday", "attempts"] == 2
    assert result["dpd_rates"].loc[result["dpd_rates"]["dpd_band"] == "1-30", "ptp_rate"].iloc[0] == 1.0
    assert result["keep_rates"].loc[result["keep_rates"]["days_to_promise"] == 3, "kept_rate"].iloc[0] == 1.0