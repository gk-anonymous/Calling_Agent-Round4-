from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def load_data(accounts_path: str | Path, calls_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    accounts = pd.read_csv(accounts_path)
    calls = pd.read_csv(calls_path, parse_dates=["called_at"])
    return accounts, calls


def analyze_calls(accounts: pd.DataFrame, calls: pd.DataFrame) -> dict[str, pd.DataFrame | dict[str, float | int]]:
    enriched = calls.merge(accounts[["account_id", "state", "batch", "dpd", "outstanding"]], on="account_id", validate="many_to_one")
    enriched["connected"] = enriched["disposition"].ne("NO_ANSWER")
    enriched["rpc"] = enriched["disposition"].isin(["PTP", "RPC_NO_PTP"])
    enriched["ptp"] = enriched["disposition"].eq("PTP")
    enriched["hour"] = enriched["called_at"].dt.hour
    enriched["day_type"] = enriched["called_at"].dt.dayofweek.ge(5).map({True: "Weekend", False: "Weekday"})

    hourly = enriched.groupby("hour", as_index=False).agg(
        attempts=("connected", "size"), connect_rate=("connected", "mean")
    )
    weekpart = enriched.groupby("day_type", as_index=False).agg(
        attempts=("connected", "size"), connect_rate=("connected", "mean")
    )

    enriched["dpd_band"] = pd.cut(
        enriched["dpd"], bins=[0, 30, 60, 90, 120], labels=["1-30", "31-60", "61-90", "91-120"]
    )
    dpd_rates = enriched.groupby("dpd_band", observed=False).agg(
        rpc=("rpc", "sum"), ptp=("ptp", "sum")
    ).reset_index()
    dpd_rates["ptp_rate"] = dpd_rates["ptp"].div(dpd_rates["rpc"].replace(0, pd.NA))

    ptp_rows = enriched[enriched["ptp"]].copy()
    ptp_rows["days_to_promise"] = ptp_rows["days_to_promise"].astype(int)
    keep_rates = ptp_rows.groupby("days_to_promise", as_index=False).agg(
        ptps=("ptp_kept", "size"), kept_rate=("ptp_kept", "mean")
    )

    target = enriched[enriched["state"].eq("BR") & enriched["batch"].eq("B7")]
    target_connected = target[target["connected"]]
    baseline_connected = enriched[
        enriched["connected"] & ~(enriched["state"].eq("BR") & enriched["batch"].eq("B7"))
    ]
    target_wrong_rate = float(target_connected["disposition"].eq("WRONG_NUMBER").mean())
    baseline_wrong_rate = float(baseline_connected["disposition"].eq("WRONG_NUMBER").mean())
    anomaly = {
        "target_attempts": len(target),
        "target_connected": len(target_connected),
        "target_wrong": int(target_connected["disposition"].eq("WRONG_NUMBER").sum()),
        "target_wrong_rate": target_wrong_rate,
        "baseline_wrong_rate": baseline_wrong_rate,
        "rate_ratio": target_wrong_rate / baseline_wrong_rate if baseline_wrong_rate else float("inf"),
    }
    return {
        "enriched": enriched,
        "hourly": hourly,
        "weekpart": weekpart,
        "dpd_rates": dpd_rates,
        "keep_rates": keep_rates,
        "anomaly": anomaly,
    }


def save_connect_chart(hourly: pd.DataFrame, weekpart: pd.DataFrame, path: str | Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    axes[0].bar(hourly["hour"], hourly["connect_rate"] * 100, color="#176b87")
    axes[0].set(title="Connect rate by hour", xlabel="Hour of day", ylabel="Connected calls (%)", xticks=hourly["hour"])
    axes[1].bar(weekpart["day_type"], weekpart["connect_rate"] * 100, color=["#176b87", "#e07a3f"])
    axes[1].set(title="Connect rate by day type", ylabel="Connected calls (%)")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def write_memo(analysis: dict, output_path: str | Path) -> str:
    hourly = analysis["hourly"]
    weekpart = analysis["weekpart"].set_index("day_type")
    anomaly = analysis["anomaly"]
    best = hourly.loc[hourly["connect_rate"].idxmax()]
    worst = hourly.loc[hourly["connect_rate"].idxmin()]
    weekday_rate = weekpart.loc["Weekday", "connect_rate"]
    weekend_rate = weekpart.loc["Weekend", "connect_rate"]
    memo = f"""# Collections Campaign Memo

**To:** Collections Head<br>
**Subject:** August dialer results and immediate actions

The generated sample contains {len(analysis['enriched']):,} call attempts. All rates below are call-level estimates from this synthetic dataset; validate against production before changing lender policy.

1. **Time-weight capacity toward the strongest hour.** Hour {int(best['hour']):02d}:00 connected at {best['connect_rate']:.1%}, versus {worst['connect_rate']:.1%} at {int(worst['hour']):02d}:00. Moving 1,000 attempts from the weakest to strongest hour would imply about {(best['connect_rate'] - worst['connect_rate']) * 1000:.0f} additional connects, assuming comparable account mix and no saturation.
2. **Quarantine and audit batch B7 in Bihar.** {anomaly['target_wrong']:,} of {anomaly['target_connected']:,} connects ({anomaly['target_wrong_rate']:.1%}) were wrong-party, against {anomaly['baseline_wrong_rate']:.1%} elsewhere ({anomaly['rate_ratio']:.1f}x). Pause or suppress this segment, validate phone mapping, then resume only after a controlled sample passes.
3. **Plan weekday/weekend staffing from measured lift.** Weekday connect rate was {weekday_rate:.1%}; weekend was {weekend_rate:.1%}. At 1,000 attempts, the observed difference corresponds to {(weekend_rate - weekday_rate) * 1000:+.0f} connects on weekends. Run a balanced time/state experiment before permanently moving capacity.

**Caveat:** This is seeded synthetic data with an injected B7/BR wrong-number effect. These figures validate the analysis workflow, not actual campaign performance.
"""
    Path(output_path).write_text(memo, encoding="utf-8")
    return memo