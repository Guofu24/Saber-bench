# Prompt khởi động Claude Code — lấy subtask thật làm gốc

```text
Read @CLAUDE.md, @docs/SUBTASK_SCOPE.md,
@docs/SUBTASK_CONTRACT.md, @docs/GRADER_CONTRACT.md,
@docs/IMPLEMENTATION_SEQUENCE.md, @docs/SECURITY.md,
and @tasks/DOMAIN_BACKLOG.md.

Important: Engineering T001-T038 are implementation PRs, NOT the
55 NICE tasks nor the 175 operational benchmark subtasks.

First inspect repository state; do NOT claim that fixtures, VM images,
SOAR cases, hidden labels, or verifiers exist unless you locate them.

Target benchmark subtask: T1112.001.
Read @tasks/subtasks/T1112.001.md and the exact source record
in @catalog/subtasks.json.

In PLAN MODE, propose a minimal vertical slice implementing:
- manifest and output DTO for verdict;
- HV-01 input fixture and evaluator-only gold label;
- deterministic scorer with positive, negative, invalid tests;
- isolated episode runner and JSON report;
- exact files/dependencies, test commands, blockers and acceptance.

If foundational engineering tasks are missing, plan those dependencies
as separate PRs. Do not replace source task semantics with a generic
"SOC agent demo". No source editing in plan mode. No infra apply,
attack execution, real host response or live customer data access.
```

Sau khi duyệt plan (trong Claude Code ngoài plan mode):

```text
Implement only the approved minimal PR or the approved T1112.001
subtask slice. Keep the original source scoring contract, isolate private
truth, write failing tests first, run all relevant quality gates, and
report exact commands/results. If required data or lab authorization is
missing, mark the integration BLOCKED; never substitute a mocked PASS.
Do not start another subtask automatically.
```

Để chọn bài bất kỳ:

```bash
python scripts/validate_catalog.py
python scripts/show_subtask.py T0020.001
python scripts/show_subtask.py T1487.001
```

Lệnh Python ở trên chạy được trong **planning kit**; các lệnh `saber task ...` ở roadmap là sản phẩm Claude Code cần hiện thực hóa, **chưa có trong ZIP**.
