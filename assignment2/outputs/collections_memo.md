# Collections Campaign Memo

**To:** Collections Head<br>
**Subject:** August dialer results and immediate actions

The generated sample contains 70,235 call attempts. All rates below are call-level estimates from this synthetic dataset; validate against production before changing lender policy.

1. **Time-weight capacity toward the strongest hour.** Hour 18:00 connected at 33.6%, versus 21.2% at 12:00. Moving 1,000 attempts from the weakest to strongest hour would imply about 123 additional connects, assuming comparable account mix and no saturation.
2. **Quarantine and audit batch B7 in Bihar.** 114 of 213 connects (53.5%) were wrong-party, against 7.8% elsewhere (6.8x). Pause or suppress this segment, validate phone mapping, then resume only after a controlled sample passes.
3. **Plan weekday/weekend staffing from measured lift.** Weekday connect rate was 23.8%; weekend was 29.3%. At 1,000 attempts, the observed difference corresponds to +54 connects on weekends. Run a balanced time/state experiment before permanently moving capacity.

**Caveat:** This is seeded synthetic data with an injected B7/BR wrong-number effect. These figures validate the analysis workflow, not actual campaign performance.
