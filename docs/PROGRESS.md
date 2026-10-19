# SABER implementation progress (machine-generated from status/ledger.json)

Updated: 2026-10-19T03:36:47+00:00

Status meanings: `DONE_DEV`/`IMPLEMENTED_DEV` = implementation + independent offline tests ran green;
`PARTIAL` = safe parts done, remainder listed in blockers; `BLOCKED_INTEGRATION` = needs external
lab/SIEM/VM/data; `PENDING` = not started. **Nothing here is READY_BENCHMARK**: that requires
independently validated private data, lab verification and human adjudication.

## Summary

| Kind | BLOCKED | BLOCKED_INTEGRATION | DONE_DEV | IMPLEMENTED_DEV | PARTIAL | PENDING |
|---|---|---|---|---|---|---|
| engineering | 0 | 4 | 6 | 0 | 0 | 28 |
| bridge | 0 | 0 | 5 | 0 | 0 | 0 |
| domain | 0 | 0 | 0 | 12 | 0 | 163 |

## Items

| ID | Kind | Phase | Status | Tests | Blockers / notes |
|---|---|---|---|---|---|
| T001 | engineering | foundation | DONE_DEV | `uv run ruff check src tests scripts`<br>`uv run ruff format --check src tests`<br>`uv run mypy`<br>`uv run pytest` | CI not run remotely yet (no push at time of record). Windows host; uv project venv. |
| T002 | engineering | foundation | DONE_DEV | `uv run pytest tests/unit/domain/test_contracts.py`<br>`uv run mypy` | Pydantic v2 strict DTOs; no DB/API. |
| T003 | engineering | foundation | PENDING |  |  |
| T004 | engineering | foundation | PENDING |  |  |
| T005 | engineering | foundation | PENDING |  |  |
| B001 | bridge | bridge | DONE_DEV | `uv run pytest tests/unit/catalog/test_loader.py` | 175 items parsed, 0 CUSTOM aggregates, weights verified; source hash verified. |
| B002 | bridge | bridge | DONE_DEV | `uv run pytest tests/unit/domain/test_subtask_spec.py` | SubtaskSpecV1 builds for all 175 records; env-specific invariants enforced. |
| B003 | bridge | bridge | DONE_DEV | `uv run pytest tests/unit/grading`<br>`uv run mypy` | Conventions in docs/adr/0001; real YARA/Suricata/hypervisor adapters remain BLOCKED_INTEGRATION. |
| B004 | bridge | bridge | DONE_DEV | `uv run pytest tests/security/test_truth_isolation.py` | Episode builder: public manifest + sealed truth split; leak guard on public payload. |
| B005 | bridge | bridge | DONE_DEV | `uv run pytest tests/unit/test_cli.py` | CLI: task list/show/build/run/grade/report + smoke; deterministic reports labelled DEV_SIMULATION_ONLY. |
| T006 | engineering | offline_engine | PENDING |  |  |
| T007 | engineering | offline_engine | PENDING |  |  |
| T008 | engineering | offline_engine | DONE_DEV | `uv run pytest tests/security/test_query_guards.py` | FakeEventStore: deterministic, visibility-aware, episode-isolated, paginated. |
| T009 | engineering | offline_engine | DONE_DEV | `uv run pytest tests/security/test_query_guards.py` | Bounded gateway: server-bound as_of/episode, HMAC cursors, budgets, audited denials. OpenSearch/Wazuh adapter = T018 BLOCKED_INTEGRATION. |
| T010 | engineering | offline_engine | PENDING |  |  |
| T011 | engineering | offline_engine | PENDING |  |  |
| T012 | engineering | offline_engine | PENDING |  |  |
| T013 | engineering | offline_engine | PENDING |  |  |
| T014 | engineering | offline_engine | PENDING |  |  |
| T1112.001 | domain | pilot_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1112_001.py` | No independently-sourced private gold labels / expert adjudication; synthetic DEV fixtures only — Oracle reaches full credit on all variants; reference B0 baseline present. DEV_SIMULATION_ONLY. |
| T1348.001 | domain | pilot_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1348_001.py` | No independently-sourced private gold labels / expert adjudication; synthetic DEV fixtures only — Oracle reaches full credit on all variants; reference B0 baseline present. DEV_SIMULATION_ONLY. |
| T2012.001 | domain | pilot_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t2012_001.py` | No independently-sourced private gold labels / expert adjudication; synthetic DEV fixtures only — Oracle reaches full credit on all variants; reference B0 baseline present. DEV_SIMULATION_ONLY. |
| T0020.001 | domain | pilot_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t0020_001.py` | No independently-sourced private gold labels / expert adjudication; synthetic DEV fixtures only — Oracle reaches full credit on all variants; reference B0 baseline present. DEV_SIMULATION_ONLY. |
| T0173.001 | domain | pilot_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t0173_001.py` | No independently-sourced private gold labels / expert adjudication; synthetic DEV fixtures only — Oracle reaches full credit on all variants; reference B0 baseline present. DEV_SIMULATION_ONLY. |
| T015 | engineering | range_adapters | DONE_DEV | `uv run pytest tests/unit/test_lab_plan_and_config.py` | Real Proxmox apply requires operator credentials + H1/H2 gates — Plan-only isolation validator; rejects prod routes/NAT/egress. No apply path exists. |
| T016 | engineering | range_adapters | PENDING |  |  |
| T017 | engineering | range_adapters | BLOCKED_INTEGRATION |  | No approved MinIO/S3 object store — RawEvidenceStore port defined; compose service scaffolded. |
| T018 | engineering | range_adapters | BLOCKED_INTEGRATION |  | No approved/reachable/authenticated OpenSearch or Wazuh Indexer — EventQuery->backend DSL translation implemented+tested; live search fails closed. |
| T019 | engineering | range_adapters | PENDING |  |  |
| T020 | engineering | range_adapters | PENDING |  |  |
| T021 | engineering | range_adapters | PENDING |  |  |
| T022 | engineering | range_adapters | PENDING |  |  |
| T023 | engineering | range_adapters | BLOCKED_INTEGRATION |  | No isolated lab + operator approval for emulation — Allowlisted-emulation driver lists profiles, refuses execution (fail closed). |
| T024 | engineering | range_adapters | BLOCKED_INTEGRATION |  | No hypervisor lab; real snapshot/verify needs H2 — RangeController port + DEV LocalDirMachine capture; hypervisor adapter fails closed. |
| T025 | engineering | agents | PENDING |  |  |
| T026 | engineering | agents | PENDING |  |  |
| T027 | engineering | agents | PENDING |  |  |
| T028 | engineering | agents | PENDING |  |  |
| T029 | engineering | agents | PENDING |  |  |
| T030 | engineering | agents | DONE_DEV | `uv run pytest tests/security/test_response_actions.py` | Real lab side-effect execution requires approved isolated lab + executor token (H4) — Dry-run default; track-A no side effects; approval binds exact action; BlockedLabResponseDriver fails closed. |
| T031 | engineering | agents | PENDING |  |  |
| T032 | engineering | agents | PENDING |  |  |
| T0167.001 | domain | subtasks_file | PENDING |  |  |
| T0167.002 | domain | subtasks_file | PENDING |  |  |
| T0167.003 | domain | subtasks_file | PENDING |  |  |
| T0173.002 | domain | subtasks_file | PENDING |  |  |
| T0182.001 | domain | subtasks_file | PENDING |  |  |
| T0182.002 | domain | subtasks_file | PENDING |  |  |
| T0182.003 | domain | subtasks_file | PENDING |  |  |
| T0292.001 | domain | subtasks_file | PENDING |  |  |
| T0292.002 | domain | subtasks_file | PENDING |  |  |
| T0397.001 | domain | subtasks_file | PENDING |  |  |
| T0397.002 | domain | subtasks_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t0397_002.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T0510.001 | domain | subtasks_file | PENDING |  |  |
| T0510.002 | domain | subtasks_file | PENDING |  |  |
| T0845.001 | domain | subtasks_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t0845_001.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T0845.002 | domain | subtasks_file | PENDING |  |  |
| T1053.001 | domain | subtasks_file | PENDING |  |  |
| T1053.002 | domain | subtasks_file | PENDING |  |  |
| T1085.001 | domain | subtasks_file | PENDING |  |  |
| T1085.002 | domain | subtasks_file | PENDING |  |  |
| T1090.001 | domain | subtasks_file | PENDING |  |  |
| T1090.002 | domain | subtasks_file | PENDING |  |  |
| T1090.003 | domain | subtasks_file | PENDING |  |  |
| T1102.001 | domain | subtasks_file | PENDING |  |  |
| T1102.002 | domain | subtasks_file | PENDING |  |  |
| T1103.001 | domain | subtasks_file | PENDING |  |  |
| T1103.002 | domain | subtasks_file | PENDING |  |  |
| T1104.001 | domain | subtasks_file | PENDING |  |  |
| T1104.002 | domain | subtasks_file | PENDING |  |  |
| T1104.003 | domain | subtasks_file | PENDING |  |  |
| T1111.001 | domain | subtasks_file | PENDING |  |  |
| T1111.002 | domain | subtasks_file | PENDING |  |  |
| T1112.002 | domain | subtasks_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1112_002.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T1241.001 | domain | subtasks_file | PENDING |  |  |
| T1241.002 | domain | subtasks_file | PENDING |  |  |
| T1242.001 | domain | subtasks_file | PENDING |  |  |
| T1242.002 | domain | subtasks_file | PENDING |  |  |
| T1250.001 | domain | subtasks_file | PENDING |  |  |
| T1250.002 | domain | subtasks_file | PENDING |  |  |
| T1251.001 | domain | subtasks_file | PENDING |  |  |
| T1251.002 | domain | subtasks_file | PENDING |  |  |
| T1251.003 | domain | subtasks_file | PENDING |  |  |
| T1252.001 | domain | subtasks_file | PENDING |  |  |
| T1252.002 | domain | subtasks_file | PENDING |  |  |
| T1253.001 | domain | subtasks_file | PENDING |  |  |
| T1253.002 | domain | subtasks_file | PENDING |  |  |
| T1253.003 | domain | subtasks_file | PENDING |  |  |
| T1257.001 | domain | subtasks_file | PENDING |  |  |
| T1257.002 | domain | subtasks_file | PENDING |  |  |
| T1257.003 | domain | subtasks_file | PENDING |  |  |
| T1290.001 | domain | subtasks_file | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1290_001.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T1290.002 | domain | subtasks_file | PENDING |  |  |
| T1299.001 | domain | subtasks_file | PENDING |  |  |
| T1299.002 | domain | subtasks_file | PENDING |  |  |
| T1315.001 | domain | subtasks_file | PENDING |  |  |
| T1315.002 | domain | subtasks_file | PENDING |  |  |
| T1316.001 | domain | subtasks_file | PENDING |  |  |
| T1316.002 | domain | subtasks_file | PENDING |  |  |
| T1323.001 | domain | subtasks_file | PENDING |  |  |
| T1323.002 | domain | subtasks_file | PENDING |  |  |
| T1324.001 | domain | subtasks_file | PENDING |  |  |
| T1324.002 | domain | subtasks_file | PENDING |  |  |
| T1324.003 | domain | subtasks_file | PENDING |  |  |
| T1332.001 | domain | subtasks_file | PENDING |  |  |
| T1332.002 | domain | subtasks_file | PENDING |  |  |
| T1332.003 | domain | subtasks_file | PENDING |  |  |
| T1341.001 | domain | subtasks_file | PENDING |  |  |
| T1341.002 | domain | subtasks_file | PENDING |  |  |
| T1347.001 | domain | subtasks_file | PENDING |  |  |
| T1347.002 | domain | subtasks_file | PENDING |  |  |
| T1348.002 | domain | subtasks_file | PENDING |  |  |
| T1349.001 | domain | subtasks_file | PENDING |  |  |
| T1349.002 | domain | subtasks_file | PENDING |  |  |
| T1350.001 | domain | subtasks_file | PENDING |  |  |
| T1350.002 | domain | subtasks_file | PENDING |  |  |
| T1351.001 | domain | subtasks_file | PENDING |  |  |
| T1351.002 | domain | subtasks_file | PENDING |  |  |
| T1371.001 | domain | subtasks_file | PENDING |  |  |
| T1371.002 | domain | subtasks_file | PENDING |  |  |
| T1381.001 | domain | subtasks_file | PENDING |  |  |
| T1384.001 | domain | subtasks_file | PENDING |  |  |
| T1384.002 | domain | subtasks_file | PENDING |  |  |
| T1386.001 | domain | subtasks_file | PENDING |  |  |
| T1386.002 | domain | subtasks_file | PENDING |  |  |
| T1387.001 | domain | subtasks_file | PENDING |  |  |
| T1387.002 | domain | subtasks_file | PENDING |  |  |
| T1388.001 | domain | subtasks_file | PENDING |  |  |
| T1388.002 | domain | subtasks_file | PENDING |  |  |
| T1391.001 | domain | subtasks_file | PENDING |  |  |
| T1391.002 | domain | subtasks_file | PENDING |  |  |
| T1406.001 | domain | subtasks_file | PENDING |  |  |
| T1406.002 | domain | subtasks_file | PENDING |  |  |
| T1428.001 | domain | subtasks_file | PENDING |  |  |
| T1428.002 | domain | subtasks_file | PENDING |  |  |
| T1607.001 | domain | subtasks_file | PENDING |  |  |
| T1607.002 | domain | subtasks_file | PENDING |  |  |
| T1617.001 | domain | subtasks_file | PENDING |  |  |
| T1617.002 | domain | subtasks_file | PENDING |  |  |
| T1617.003 | domain | subtasks_file | PENDING |  |  |
| T1644.001 | domain | subtasks_file | PENDING |  |  |
| T1644.002 | domain | subtasks_file | PENDING |  |  |
| T2012.002 | domain | subtasks_file | PENDING |  |  |
| T2013.001 | domain | subtasks_file | PENDING |  |  |
| T2013.002 | domain | subtasks_file | PENDING |  |  |
| T2016.001 | domain | subtasks_file | PENDING |  |  |
| T2016.002 | domain | subtasks_file | PENDING |  |  |
| T0020.002 | domain | subtasks_soc | PENDING |  |  |
| T0020.003 | domain | subtasks_soc | PENDING |  |  |
| T0173.003 | domain | subtasks_soc | PENDING |  |  |
| T0292.003 | domain | subtasks_soc | PENDING |  |  |
| T0510.003 | domain | subtasks_soc | PENDING |  |  |
| T0845.003 | domain | subtasks_soc | PENDING |  |  |
| T1053.003 | domain | subtasks_soc | PENDING |  |  |
| T1085.003 | domain | subtasks_soc | PENDING |  |  |
| T1103.003 | domain | subtasks_soc | PENDING |  |  |
| T1111.003 | domain | subtasks_soc | PENDING |  |  |
| T1112.003 | domain | subtasks_soc | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1112_003.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T1241.003 | domain | subtasks_soc | PENDING |  |  |
| T1242.003 | domain | subtasks_soc | PENDING |  |  |
| T1250.003 | domain | subtasks_soc | PENDING |  |  |
| T1252.003 | domain | subtasks_soc | PENDING |  |  |
| T1290.003 | domain | subtasks_soc | PENDING |  |  |
| T1299.003 | domain | subtasks_soc | PENDING |  |  |
| T1315.003 | domain | subtasks_soc | PENDING |  |  |
| T1316.003 | domain | subtasks_soc | PENDING |  |  |
| T1323.003 | domain | subtasks_soc | PENDING |  |  |
| T1347.003 | domain | subtasks_soc | PENDING |  |  |
| T1348.003 | domain | subtasks_soc | PENDING |  |  |
| T1348.004 | domain | subtasks_soc | PENDING |  |  |
| T1348.005 | domain | subtasks_soc | PENDING |  |  |
| T1348.006 | domain | subtasks_soc | PENDING |  |  |
| T1348.007 | domain | subtasks_soc | PENDING |  |  |
| T1348.008 | domain | subtasks_soc | PENDING |  |  |
| T1348.009 | domain | subtasks_soc | PENDING |  |  |
| T1348.010 | domain | subtasks_soc | PENDING |  |  |
| T1348.011 | domain | subtasks_soc | PENDING |  |  |
| T1348.012 | domain | subtasks_soc | PENDING |  |  |
| T1348.013 | domain | subtasks_soc | PENDING |  |  |
| T1349.003 | domain | subtasks_soc | PENDING |  |  |
| T1350.003 | domain | subtasks_soc | PENDING |  |  |
| T1351.003 | domain | subtasks_soc | PENDING |  |  |
| T1371.003 | domain | subtasks_soc | PENDING |  |  |
| T1384.003 | domain | subtasks_soc | PENDING |  |  |
| T1386.003 | domain | subtasks_soc | PENDING |  |  |
| T1387.003 | domain | subtasks_soc | PENDING |  |  |
| T1388.003 | domain | subtasks_soc | PENDING |  |  |
| T1391.003 | domain | subtasks_soc | PENDING |  |  |
| T1406.003 | domain | subtasks_soc | PENDING |  |  |
| T1428.003 | domain | subtasks_soc | PENDING |  |  |
| T1607.003 | domain | subtasks_soc | PENDING |  |  |
| T1644.003 | domain | subtasks_soc | PENDING |  |  |
| T2013.003 | domain | subtasks_soc | PENDING |  |  |
| T2016.003 | domain | subtasks_soc | PENDING |  |  |
| T0397.003 | domain | subtasks_vm | PENDING |  |  |
| T1102.003 | domain | subtasks_vm | PENDING |  |  |
| T1109.001 | domain | subtasks_vm | PENDING |  |  |
| T1109.002 | domain | subtasks_vm | PENDING |  |  |
| T1109.003 | domain | subtasks_vm | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1109_003.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T1341.003 | domain | subtasks_vm | PENDING |  |  |
| T1370.001 | domain | subtasks_vm | PENDING |  |  |
| T1370.002 | domain | subtasks_vm | PENDING |  |  |
| T1370.003 | domain | subtasks_vm | PENDING |  |  |
| T1381.002 | domain | subtasks_vm | PENDING |  |  |
| T1381.003 | domain | subtasks_vm | PENDING |  |  |
| T1389.001 | domain | subtasks_vm | PENDING |  |  |
| T1389.002 | domain | subtasks_vm | PENDING |  |  |
| T1389.003 | domain | subtasks_vm | PENDING |  |  |
| T1487.001 | domain | subtasks_vm | PENDING |  |  |
| T1487.002 | domain | subtasks_vm | PENDING |  |  |
| T1487.003 | domain | subtasks_vm | IMPLEMENTED_DEV | `uv run pytest tests/subtasks/test_t1487_003.py` | Synthetic DEV fixtures; no independently-sourced private gold labels / expert adjudication — Oracle reaches full credit; DEV_SIMULATION_ONLY |
| T2012.003 | domain | subtasks_vm | PENDING |  |  |
| T033 | engineering | evaluation_release | PENDING |  |  |
| T034 | engineering | evaluation_release | PENDING |  |  |
| T035 | engineering | evaluation_release | PENDING |  |  |
| T036 | engineering | evaluation_release | PENDING |  |  |
| T037 | engineering | evaluation_release | PENDING |  |  |
| T038 | engineering | evaluation_release | PENDING |  |  |
