"""CLI smoke/integration tests via Click's test runner (offline)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from saber.cli.main import cli


def _run(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(cli, list(args))
    return result.exit_code, result.output


def test_version() -> None:
    code, out = _run("--version")
    assert code == 0 and "saber" in out


def test_task_list_implemented() -> None:
    code, out = _run("task", "list", "--implemented")
    assert code == 0
    assert "T1112.001" in out and "implemented)" in out


def test_task_show_json() -> None:
    code, out = _run("task", "show", "T1112.001")
    assert code == 0
    payload = json.loads(out)
    assert payload["id"] == "T1112.001"
    assert payload["parsed_aggregate"]["kind"] == "fixed_item"
    assert payload["implemented"] is True


def test_task_run_oracle_and_reference() -> None:
    for solver in ("oracle", "reference"):
        code, out = _run(
            "task", "run", "T1348.001", "--solver", solver, "--variant", "dense", "--seed", "3"
        )
        assert code == 0, out
        payload = json.loads(out)
        assert payload["validity"] == "VALID"
        assert payload["score"] == 1.0
        assert payload["labels"] == ["DEV_SIMULATION_ONLY"]


def test_smoke_command() -> None:
    code, out = _run("smoke", "--subtask", "T2012.001", "--seed", "7")
    assert code == 0, out
    assert "SMOKE OK" in out


def test_build_writes_split_directories(tmp_path: object) -> None:
    out_dir = str(tmp_path)  # type: ignore[arg-type]
    code, out = _run("task", "build", "T0173.001", "--seed", "5", "--out", out_dir)
    assert code == 0, out
    payload = json.loads(out)
    assert payload["subtask_id"] == "T0173.001"
    assert "sealed" in payload["files"] and "manifest" in payload["files"]


def test_report_command() -> None:
    code, out = _run("task", "report", "T1112.001", "--seeds", "1,2,42")
    assert code == 0, out
    payload = json.loads(out)
    assert payload["oracle_full_credit"] is True
    assert payload["labels"] == ["DEV_SIMULATION_ONLY"]
    assert payload["scorer_version"] == "score_v1"
