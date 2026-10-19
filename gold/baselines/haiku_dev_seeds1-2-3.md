# Gold baseline run — haiku / dev / seeds [1, 2, 3]

- Generated: 2026-10-19T08:36:35+00:00
- Auth: claude.ai subscription CLI; the runner scrubs API-key/provider env vars and does not itself introduce API billing, but cannot override operator apiKeyHelper/settings/stored credentials (operator responsibility). provider/cost_basis recorded for audit; cost is LIST price, informational only.
- Models observed: ['claude-haiku-4-5']  providers: ['firstParty']
- Labels: GOLD_PILOT_V1, LLM_BASELINE_CLI_SUBSCRIPTION, DEV_SIMULATION_ONLY
- Measurement of discrimination only; NOT an externally validated benchmark and NOT READY_BENCHMARK.

## Summary (mean over episodes; 95% CI = cluster bootstrap over pilots)

- episodes: 36 (12 pilots x 3 seeds)
- CI method: cluster bootstrap resampling the pilots (seeds within a pilot are correlated)
- oracle: 1.0 clusterCI95[1.0,1.0]
- rules (naive): 0.4398 clusterCI95[0.2598,0.6106]
- oracle − rules (paired): 0.5602 clusterCI95[0.3894,0.7402]
- LLM completion rate: 0.9722
- LLM score (completed): 0.9436 clusterCI95[0.8792,0.9914]
- LLM score (all episodes): 0.9174 clusterCI95[0.8391,0.9809]
- LLM − rules (paired, completed): 0.5055 clusterCI95[0.342,0.6691]
- LLM latency: mean 19948 ms, p95 69101 ms  tool failures: 1
- LLM incomplete episodes: [{'subtask_id': 'T1112.002', 'seed': 1, 'reason': 'timeout'}]
- LLM list-price cost (informational): $1.2113

## Per-seed (run-to-run variability; 3 seeds = limited evidence of stability)

| Seed | Oracle | Rules | LLM completed | Completion |
|---|---|---|---|---|
| 1 | 1.0 | 0.3462 | 0.9568 | 0.9167 |
| 2 | 1.0 | 0.4948 | 0.9744 | 1.0 |
| 3 | 1.0 | 0.4785 | 0.9007 | 1.0 |

## Per-pilot (mean over seeds)

| Subtask | Svc | Oracle | Rules | LLM | Completion |
|---|---|---|---|---|---|
| T1112.002 | MON | 1.0 | 0.8333 | 1.0 | 0.6667 |
| T1348.002 | MON | 1.0 | 0.5354 | 1.0 | 1.0 |
| T1387.002 | MON | 1.0 | 0.4 | 0.6667 | 1.0 |
| T0020.001 | CNT | 1.0 | 0.3083 | 1.0 | 1.0 |
| T1406.001 | CNT | 1.0 | 0.9024 | 1.0 | 1.0 |
| T1111.002 | CNT | 1.0 | 0.0 | 0.9 | 1.0 |
| T2013.001 | HUNT | 1.0 | 0.0 | 0.9354 | 1.0 |
| T1102.002 | HUNT | 1.0 | 0.7895 | 1.0 | 1.0 |
| T0167.002 | HUNT | 1.0 | 0.6316 | 1.0 | 1.0 |
| T0173.002 | IR | 1.0 | 0.4939 | 1.0 | 1.0 |
| T0397.002 | IR | 1.0 | 0.3833 | 1.0 | 1.0 |
| T1324.002 | IR | 1.0 | 0.0 | 0.84 | 1.0 |
