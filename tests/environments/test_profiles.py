import json

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from saber.cli.main import cli
from saber.environments.models import EnvironmentConfig, Service


@pytest.mark.parametrize("profile", ["local", "sandbox", "vm", "remote"])
def test_profile_round_trip_and_no_overwrite(tmp_path, profile):
    runner = CliRunner()
    path = tmp_path / "env.json"
    args = ["env", "init", "--profile", profile, "--out", str(path), "--clients", "2"]
    assert runner.invoke(cli, args).exit_code == 0
    config = EnvironmentConfig.model_validate_json(path.read_text())
    assert config.profile == profile and len(config.world.actors) == 11
    original = path.read_bytes()
    assert runner.invoke(cli, args).exit_code != 0
    assert path.read_bytes() == original
    result = runner.invoke(cli, ["env", "validate", "--config", str(path)])
    assert result.exit_code == 0 and json.loads(result.output)["valid"]


@pytest.mark.parametrize(
    "url",
    ["http://user:secret@localhost", "https://x/?key=secret", "file:///x", "http://x/#secret"],
)
def test_inline_credentials_and_non_http_urls_rejected(url):
    with pytest.raises(ValidationError):
        Service(name="test", capability="siem", api_base_url=url)


@pytest.mark.parametrize(
    "path", ["//evil.test", "/../private", "/health?key=x", "https://evil.test", "/%2fother"]
)
def test_health_path_cannot_override_target(path):
    with pytest.raises(ValidationError):
        Service(
            name="test",
            capability="siem",
            api_base_url="https://example.test",
            health_check_path=path,
        )


def test_invalid_config_does_not_echo_secrets(tmp_path):
    path = tmp_path / "env.json"
    path.write_text(json.dumps({"name": "test", "profile": "local", "api_key": "DO-NOT-PRINT"}))
    result = CliRunner().invoke(cli, ["env", "validate", "--config", str(path)])
    assert result.exit_code != 0 and "DO-NOT-PRINT" not in result.output


def test_profiles_are_explicit_about_unimplemented_capabilities():
    result = CliRunner().invoke(cli, ["env", "list"])
    profiles = json.loads(result.output)
    assert {p["profile"] for p in profiles} == {"local", "sandbox", "vm", "remote"}
    assert all("DEV_SIMULATION_ONLY" in p["labels"] and p["not_implemented"] for p in profiles)
