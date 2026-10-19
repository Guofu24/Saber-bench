# SABER subtask coverage matrix (machine-generated)

Updated: 2026-10-19T05:03:53+00:00

Readiness tiers are strict: SPECIFIED (contract only), IMPLEMENTED_OFFLINE (code+tests),
VERIFIED_OFFLINE (tests ran green on synthetic DEV data), BLOCKED_INTEGRATION (needs a real
lab/dataset), READY_BENCHMARK (independently validated gold — never auto-set). Synthetic DEV
fixtures are never equated with validated benchmark data.

## Tally

| Status | Count |
|---|---|
| SPECIFIED | 0 |
| IMPLEMENTED_OFFLINE | 0 |
| VERIFIED_OFFLINE | 175 |
| BLOCKED_INTEGRATION | 0 |
| READY_BENCHMARK | 0 |

## Subtasks

| ID | Service | Env | Aggregate | Split | Status |
|---|---|---|---|---|---|
| T0020.001 | CNT | file | set_delta | test | VERIFIED_OFFLINE |
| T0020.002 | CNT | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T0020.003 | CNT | soc | tpr_minus_fpr | test | VERIFIED_OFFLINE |
| T0292.001 | HUNT | file | fixed_item | test | VERIFIED_OFFLINE |
| T0292.002 | HUNT | file | weighted_sum | test | VERIFIED_OFFLINE |
| T0292.003 | HUNT | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T1085.001 | MON | file | set_delta | train | VERIFIED_OFFLINE |
| T1085.002 | MON | file | mixture | train | VERIFIED_OFFLINE |
| T1085.003 | MON | soc | mixture | train | VERIFIED_OFFLINE |
| T1112.001 | MON | file | fixed_item | train | VERIFIED_OFFLINE |
| T1112.002 | MON | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1112.003 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1241.001 | MON | file | set_delta | train | VERIFIED_OFFLINE |
| T1241.002 | MON | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1241.003 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1242.001 | MON | file | fixed_item | dev | VERIFIED_OFFLINE |
| T1242.002 | MON | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1242.003 | MON | soc | weighted_sum | dev | VERIFIED_OFFLINE |
| T1290.001 | MON | file | fraction_correct | train | VERIFIED_OFFLINE |
| T1290.002 | MON | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1290.003 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1299.001 | MON | file | fixed_item | test | VERIFIED_OFFLINE |
| T1299.002 | MON | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1299.003 | MON | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T1347.001 | MON | file | set_delta | test | VERIFIED_OFFLINE |
| T1347.002 | MON | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1347.003 | MON | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T1348.001 | MON | file | set_delta | train | VERIFIED_OFFLINE |
| T1348.002 | MON | file | accuracy | train | VERIFIED_OFFLINE |
| T1348.003 | MON | soc | macro_average | train | VERIFIED_OFFLINE |
| T1348.004 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.005 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.006 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.007 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.008 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.009 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.010 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.011 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.012 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1348.013 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1349.001 | MON | file | fbeta | dev | VERIFIED_OFFLINE |
| T1349.002 | MON | file | fbeta | dev | VERIFIED_OFFLINE |
| T1349.003 | MON | soc | fbeta | dev | VERIFIED_OFFLINE |
| T1350.001 | MON | file | fixed_item | test | VERIFIED_OFFLINE |
| T1350.002 | MON | file | mixture | test | VERIFIED_OFFLINE |
| T1350.003 | MON | soc | mixture | test | VERIFIED_OFFLINE |
| T1351.001 | MON | file | fixed_item | train | VERIFIED_OFFLINE |
| T1351.002 | MON | file | fixed_item | train | VERIFIED_OFFLINE |
| T1351.003 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1384.001 | CNT | file | fixed_item | train | VERIFIED_OFFLINE |
| T1384.002 | CNT | file | fbeta | train | VERIFIED_OFFLINE |
| T1384.003 | CNT | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1386.001 | MON | file | set_delta | train | VERIFIED_OFFLINE |
| T1386.002 | MON | file | fbeta | train | VERIFIED_OFFLINE |
| T1386.003 | MON | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1387.001 | MON | file | fixed_item | test | VERIFIED_OFFLINE |
| T1387.002 | MON | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1387.003 | MON | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T1388.001 | MON | file | fixed_item | train | VERIFIED_OFFLINE |
| T1388.002 | MON | file | fbeta | train | VERIFIED_OFFLINE |
| T1388.003 | MON | soc | fbeta | train | VERIFIED_OFFLINE |
| T1389.001 | MON | vm | fixed_item | train | VERIFIED_OFFLINE |
| T1389.002 | MON | vm | product_gates | train | VERIFIED_OFFLINE |
| T1389.003 | MON | vm | product_gates | train | VERIFIED_OFFLINE |
| T1391.001 | IR | file | fixed_item | train | VERIFIED_OFFLINE |
| T1391.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1391.003 | IR | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1406.001 | CNT | file | fbeta | test | VERIFIED_OFFLINE |
| T1406.002 | CNT | file | fbeta | test | VERIFIED_OFFLINE |
| T1406.003 | CNT | soc | fbeta | test | VERIFIED_OFFLINE |
| T1428.001 | MON | file | fixed_item | test | VERIFIED_OFFLINE |
| T1428.002 | MON | file | fbeta | test | VERIFIED_OFFLINE |
| T1428.003 | MON | soc | fbeta | test | VERIFIED_OFFLINE |
| T0167.001 | HUNT | file | set_delta | train | VERIFIED_OFFLINE |
| T0167.002 | HUNT | file | accuracy | train | VERIFIED_OFFLINE |
| T0167.003 | HUNT | file | weighted_sum | train | VERIFIED_OFFLINE |
| T0173.001 | IR | file | kendall_tau | train | VERIFIED_OFFLINE |
| T0173.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T0173.003 | IR | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T0182.001 | IR | file | fraction_correct | dev | VERIFIED_OFFLINE |
| T0182.002 | IR | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T0182.003 | IR | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T0397.001 | IR | file | set_delta | test | VERIFIED_OFFLINE |
| T0397.002 | IR | file | fbeta | test | VERIFIED_OFFLINE |
| T0397.003 | IR | vm | weighted_sum | test | VERIFIED_OFFLINE |
| T1090.001 | IR | file | fixed_item | train | VERIFIED_OFFLINE |
| T1090.002 | IR | file | fixed_item | train | VERIFIED_OFFLINE |
| T1090.003 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1102.001 | HUNT | file | fbeta | train | VERIFIED_OFFLINE |
| T1102.002 | HUNT | file | fbeta | train | VERIFIED_OFFLINE |
| T1102.003 | HUNT | vm | fbeta | train | VERIFIED_OFFLINE |
| T1103.001 | HUNT | file | kendall_tau | train | VERIFIED_OFFLINE |
| T1103.002 | HUNT | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1103.003 | HUNT | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1104.001 | HUNT | file | fraction_correct | dev | VERIFIED_OFFLINE |
| T1104.002 | HUNT | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1104.003 | HUNT | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1253.001 | IR | file | set_delta | train | VERIFIED_OFFLINE |
| T1253.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1253.003 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1323.001 | IR | file | fbeta | train | VERIFIED_OFFLINE |
| T1323.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1323.003 | IR | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1324.001 | IR | file | kendall_tau | train | VERIFIED_OFFLINE |
| T1324.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1324.003 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1370.001 | IR | vm | fbeta | test | VERIFIED_OFFLINE |
| T1370.002 | IR | vm | fbeta | test | VERIFIED_OFFLINE |
| T1370.003 | IR | vm | weighted_sum | test | VERIFIED_OFFLINE |
| T1371.001 | IR | file | fbeta | train | VERIFIED_OFFLINE |
| T1371.002 | IR | file | fbeta | train | VERIFIED_OFFLINE |
| T1371.003 | IR | soc | fbeta | train | VERIFIED_OFFLINE |
| T1381.001 | HUNT | file | fbeta | test | VERIFIED_OFFLINE |
| T1381.002 | HUNT | vm | fbeta | test | VERIFIED_OFFLINE |
| T1381.003 | HUNT | vm | weighted_sum | test | VERIFIED_OFFLINE |
| T1487.001 | HUNT | vm | set_delta | test | VERIFIED_OFFLINE |
| T1487.002 | HUNT | vm | weighted_sum | test | VERIFIED_OFFLINE |
| T1487.003 | HUNT | vm | weighted_sum | test | VERIFIED_OFFLINE |
| T1607.001 | IR | file | set_delta | test | VERIFIED_OFFLINE |
| T1607.002 | IR | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1607.003 | IR | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T1617.001 | IR | file | fraction_correct | train | VERIFIED_OFFLINE |
| T1617.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1617.003 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T0510.001 | IR | file | fixed_item | train | VERIFIED_OFFLINE |
| T0510.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T0510.003 | IR | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1109.001 | IR | vm | product_gates | test | VERIFIED_OFFLINE |
| T1109.002 | IR | vm | product_gates | test | VERIFIED_OFFLINE |
| T1109.003 | IR | vm | product_gates | test | VERIFIED_OFFLINE |
| T1250.001 | IR | file | fixed_item | dev | VERIFIED_OFFLINE |
| T1250.002 | IR | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1250.003 | IR | soc | weighted_sum | dev | VERIFIED_OFFLINE |
| T1251.001 | IR | file | kendall_tau | test | VERIFIED_OFFLINE |
| T1251.002 | IR | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1251.003 | IR | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1252.001 | IR | file | fbeta | test | VERIFIED_OFFLINE |
| T1252.002 | IR | file | weighted_sum | test | VERIFIED_OFFLINE |
| T1252.003 | IR | soc | weighted_sum | test | VERIFIED_OFFLINE |
| T1257.001 | IR | file | fbeta | train | VERIFIED_OFFLINE |
| T1257.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1257.003 | IR | file | macro_average | train | VERIFIED_OFFLINE |
| T1315.001 | IR | file | fbeta | train | VERIFIED_OFFLINE |
| T1315.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1315.003 | IR | soc | mixture | train | VERIFIED_OFFLINE |
| T1316.001 | IR | file | set_delta | dev | VERIFIED_OFFLINE |
| T1316.002 | IR | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1316.003 | IR | soc | weighted_sum | dev | VERIFIED_OFFLINE |
| T1332.001 | IR | file | fixed_item | train | VERIFIED_OFFLINE |
| T1332.002 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1332.003 | IR | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1111.001 | CNT | file | delta_fp_tp | train | VERIFIED_OFFLINE |
| T1111.002 | CNT | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1111.003 | CNT | soc | delta_fp_tp | train | VERIFIED_OFFLINE |
| T0845.001 | HUNT | file | technique_tactic | test | VERIFIED_OFFLINE |
| T0845.002 | HUNT | file | macro_average | test | VERIFIED_OFFLINE |
| T0845.003 | HUNT | soc | macro_average | test | VERIFIED_OFFLINE |
| T1053.001 | HUNT | file | set_delta | train | VERIFIED_OFFLINE |
| T1053.002 | HUNT | file | weighted_sum | train | VERIFIED_OFFLINE |
| T1053.003 | HUNT | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T1644.001 | CNT | file | fbeta | dev | VERIFIED_OFFLINE |
| T1644.002 | CNT | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1644.003 | CNT | soc | weighted_sum | dev | VERIFIED_OFFLINE |
| T1341.001 | HUNT | file | set_delta | dev | VERIFIED_OFFLINE |
| T1341.002 | HUNT | file | weighted_sum | dev | VERIFIED_OFFLINE |
| T1341.003 | HUNT | vm | weighted_sum | dev | VERIFIED_OFFLINE |
| T2012.001 | HUNT | file | set_delta | train | VERIFIED_OFFLINE |
| T2012.002 | HUNT | file | fbeta | train | VERIFIED_OFFLINE |
| T2012.003 | HUNT | vm | fbeta | train | VERIFIED_OFFLINE |
| T2013.001 | HUNT | file | fbeta | train | VERIFIED_OFFLINE |
| T2013.002 | HUNT | file | weighted_sum | train | VERIFIED_OFFLINE |
| T2013.003 | HUNT | soc | weighted_sum | train | VERIFIED_OFFLINE |
| T2016.001 | HUNT | file | fbeta | train | VERIFIED_OFFLINE |
| T2016.002 | HUNT | file | weighted_sum | train | VERIFIED_OFFLINE |
| T2016.003 | HUNT | soc | weighted_sum | train | VERIFIED_OFFLINE |
