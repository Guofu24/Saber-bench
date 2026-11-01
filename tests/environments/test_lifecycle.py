import json
import os
import subprocess
import sys

import pytest
from click.testing import CliRunner

from saber.cli.main import cli
from saber.environments.bundle import render_bundle
from saber.environments.lifecycle import prepare_world, sandbox_down, sandbox_up
from saber.environments.models import EnvironmentConfig
from saber.world.models import default_config


def config(profile="local"):
    return EnvironmentConfig(
        name="test",
        profile=profile,
        world=default_config(1).model_copy(update={"tick_seconds": 0.01}),
    )


@pytest.mark.parametrize("profile", ["local", "vm", "remote"])
def test_run_uses_selected_config_and_requires_target_acknowledgement(tmp_path, profile):
    path = tmp_path / "env.json"
    path.write_text(config(profile).model_dump_json())
    out = tmp_path / "world"
    args = ["env", "run", "--config", str(path), "--out", str(out), "--ticks", "2"]
    runner = CliRunner()
    if profile != "local":
        assert runner.invoke(cli, args).exit_code != 0
        assert not out.exists()
        args += ["--on-target"]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    report = json.loads((out / "report.json").read_text())
    assert report["tick"] == 2 and report["engine"] == "scripted"
    assert json.loads((out / "deployment.json").read_text())["selected_profile"] == profile
    (out / "STOP").write_text("stop")
    assert runner.invoke(cli, args).exit_code != 0
    assert json.loads((out / "report.json").read_text())["tick"] == 2
    assert runner.invoke(cli, args + ["--resume"]).exit_code == 0
    assert json.loads((out / "report.json").read_text())["tick"] == 4


def test_sandbox_never_silently_runs_locally(tmp_path):
    path = tmp_path / "env.json"
    path.write_text(config("sandbox").model_dump_json())
    result = CliRunner().invoke(
        cli, ["env", "run", "--config", str(path), "--out", str(tmp_path / "w")]
    )
    assert result.exit_code != 0 and not (tmp_path / "w").exists()


def test_existing_world_configuration_is_not_overwritten(tmp_path):
    cfg = config()
    prepare_world(cfg, tmp_path)
    original = (tmp_path / "config.json").read_bytes()
    cfg.world = default_config(2)
    with pytest.raises(ValueError, match="differs"):
        prepare_world(cfg, tmp_path)
    assert (tmp_path / "config.json").read_bytes() == original


def test_compose_arguments_preserve_data_and_require_explicit_gemini(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle with spaces"
    render_bundle(config("sandbox"), bundle)
    monkeypatch.setattr("saber.environments.lifecycle.shutil.which", lambda _: "docker")
    calls = []

    def invoke(argv, **kwargs):
        calls.append((argv, kwargs))
        return "linux" if argv[1] == "info" else ""

    monkeypatch.setattr("saber.environments.lifecycle.invoke", invoke)
    with pytest.raises(ValueError, match="together"):
        sandbox_up(bundle, llm=True)
    assert not calls
    sandbox_up(bundle)
    assert calls[-1][0][-3:] == ["up", "-d", "--build"]
    assert calls[-1][1]["extra_env"] == {"SABER_ENV_RESUME": "0"}
    key_file = tmp_path / "keys.txt"
    key_file.write_text("DO-NOT-ECHO")
    sandbox_up(bundle, llm=True, key_pool=key_file, call_budget=3, resume=True)
    assert "compose.gemini.yaml" in calls[-1][0][-4]
    assert calls[-1][1]["extra_env"]["SABER_ENV_CALL_BUDGET"] == "3"
    assert "DO-NOT-ECHO" not in str(calls)
    sandbox_down(bundle)
    assert calls[-1][0][-3:] == ["down", "--timeout", "80"]
    assert "-v" not in calls[-1][0] and "--volumes" not in calls[-1][0]


def test_exported_runtime_boots_without_original_repository(tmp_path):
    bundle = tmp_path / "bundle"
    render_bundle(config("vm"), bundle)
    environment = os.environ | {
        "PYTHONPATH": str(bundle / "source/src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SABER_ENV_LLM": "0",
        "SABER_ENV_RESUME": "0",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "saber.environments.worker",
            "--config",
            str(bundle / "environment.json"),
            "--out",
            str(tmp_path / "data"),
            "--ticks",
            "2",
        ],
        cwd=bundle / "source",
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "data/report.json").read_text())
    assert report["tick"] == 2 and report["metrics"]["requests"] > 0


def test_container_resume_is_consumed_once_and_crash_cannot_clear_later_stop(tmp_path):
    from saber.environments.worker import consume_resume

    stop = tmp_path / "STOP"
    stop.write_text("operator stop")
    consume_resume(tmp_path, "a" * 32)
    assert not stop.exists()
    stop.write_text("new operator stop")
    consume_resume(tmp_path, "a" * 32)
    assert stop.read_text() == "new operator stop"
    consume_resume(tmp_path, "0")
    assert stop.exists()
    consume_resume(tmp_path, "b" * 32)
    assert not stop.exists()
