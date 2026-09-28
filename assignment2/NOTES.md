# Assignment 2 Notes

- The supplied fixed-seed data generator is retained as `gen_data.py`; run it from this directory to create `accounts.csv` and `calls.csv`.
- Connect rate is the fraction of call attempts whose disposition is not `NO_ANSWER`. RPC excludes `WRONG_NUMBER`; PTP rate is PTP divided by RPC.
- The B7/BR wrong-party rate is measured only among connected calls and compared with all other connected calls.
- The memo's 1,000-call estimates assume comparable mix and no capacity saturation; this is synthetic data with a deliberately injected segment anomaly.
