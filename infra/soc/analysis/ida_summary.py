"""Fixed IDAPython batch script. Runs only inside an operator-licensed IDA installation."""
import json
from pathlib import Path

import ida_auto
import ida_funcs
import ida_ida
import ida_pro
import idautils

ida_auto.auto_wait()
functions = []
for address in idautils.Functions():
    if len(functions) >= 1000:
        break
    functions.append({"entry": hex(address), "name": ida_funcs.get_func_name(address)})
Path("summary.json").write_text(json.dumps({"analysis_completed": True, "processor": ida_ida.inf_get_procname(),
    "function_count": ida_funcs.get_func_qty(), "functions": functions,
    "scope": "static IDAPython analysis; no execution or maliciousness verdict"}), encoding="utf-8")
ida_pro.qexit(0)
