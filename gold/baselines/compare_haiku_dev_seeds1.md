# Strong-baseline comparison — haiku / dev / seeds [1]

- Generated: 2026-10-19T10:02:30+00:00
- Auth: claude.ai subscription CLI (API-key env scrubbed); cost is LIST price, informational
- Labels: GOLD_PILOT_V1, STRONG_BASELINE_COMPARISON, DEV_SIMULATION_ONLY
- Controlled discrimination comparison on SYNTHETIC gold episodes; NOT an externally validated benchmark and NOT READY_BENCHMARK.

## Score by baseline (cluster-bootstrap 95% CI over pilots)

Score = all episodes (LLM incompletes scored 0, mixes capability + reliability); Score(completed) = capability on completed episodes only. FP/FN totals are only where the scorer exposes them (accuracy/enum/order-less pilots show blank), so are not comparable across all pilots. The `strong` arm is a conventional CEILING — see strong.py docstring.

| Baseline | Score | Score(completed) | FP total | FN total | Completion | LLM calls | Tool fails | Latency mean/p95 ms | Cost$ |
|---|---|---|---|---|---|---|---|---|---|
| oracle | 1.0 CI95[1.0, 1.0] | — | 0 | 0 | — | — | — | —/— | — |
| naive | 0.3462 CI95[0.1762, 0.5195] | — | 14 | 15 | — | — | — | —/— | — |
| strong | 0.9667 CI95[0.9, 1.0] | — | 0 | 0 | — | — | — | —/— | — |
| single | 0.8629 CI95[0.6885, 0.9881] | 0.8629 CI95[0.6885, 0.9881] | 7 | 5 | 1.0 | 12 | 0 | 17414/88468 | 0.3861 |
| specialist | 0.7974 CI95[0.5707, 0.9881] | 0.7974 CI95[0.5707, 0.9881] | 3 | 5 | 1.0 | 12 | 0 | 21850/75932 | 0.4243 |
| multi_agent | 0.9491 CI95[0.884, 1.0] | 0.9491 CI95[0.884, 1.0] | 3 | 0 | 1.0 | 24 | 0 | 31465/122509 | 0.7431 |

## Per-pilot score (mean over seeds)

| Subtask | Svc | oracle | naive | strong | single | specialist | multi_agent |
|---|---|---|---|---|---|---|---|
| T1112.002 | MON | 1.0 | 0.5 | 1.0 | 1.0 | 1.0 | 1.0 |
| T1348.002 | MON | 1.0 | 0.2727 | 1.0 | 1.0 | 1.0 | 1.0 |
| T1387.002 | MON | 1.0 | 0.0 | 1.0 | 1.0 | 1.0 | 1.0 |
| T0020.001 | CNT | 1.0 | 0.3417 | 1.0 | 0.6667 | 1.0 | 1.0 |
| T1406.001 | CNT | 1.0 | 0.9091 | 1.0 | 0.0 | 0.0 | 1.0 |
| T1111.002 | CNT | 1.0 | 0.0 | 1.0 | 1.0 | 0.0 | 0.7 |
| T2013.001 | HUNT | 1.0 | 0.0 | 1.0 | 0.9286 | 0.9286 | 0.9286 |
| T1102.002 | HUNT | 1.0 | 0.7895 | 1.0 | 1.0 | 1.0 | 1.0 |
| T0167.002 | HUNT | 1.0 | 0.625 | 1.0 | 1.0 | 1.0 | 1.0 |
| T0173.002 | IR | 1.0 | 0.4667 | 1.0 | 1.0 | 1.0 | 1.0 |
| T0397.002 | IR | 1.0 | 0.25 | 1.0 | 1.0 | 1.0 | 1.0 |
| T1324.002 | IR | 1.0 | 0.0 | 0.6 | 0.76 | 0.64 | 0.76 |
