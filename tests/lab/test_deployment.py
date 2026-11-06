import json

import pytest
import yaml
from click.testing import CliRunner

from saber.catalog.loader import repo_root
from saber.cli.main import cli
from saber.lab.deployment import compose, initialize_secrets, render, verify_bundle
from saber.lab.models import LabSpec, preset_spec


@pytest.mark.parametrize("name", ["linux-small", "windows-ad", "expanded"])
def test_complete_bundle_has_isolated_roles_no_credentials_and_detects_changes(tmp_path, name):
    spec = preset_spec(name)
    root = tmp_path / "bundle"
    render(spec, root)
    assert (root / "SOC_COMPLETION.md").is_file()
    assert (root / "source/docs/SOC_LAB_VI.md").is_file()
    assert (root / "source/docs/HTB_TRAINING.md").is_file()
    assert (root / "source/scripts/smoke_training.py").is_file()
    for name in ("LICENSE", "NOTICE", "README.vi.md"):
        assert (root / "source" / name).read_bytes() == (repo_root() / name).read_bytes()
    assert (root / "agent-office/LICENSE").read_bytes() == (
        repo_root() / "agent-office/LICENSE"
    ).read_bytes()
    assert (root / "agent-office/THIRD_PARTY_NOTICES.txt").read_bytes() == (
        repo_root() / "agent-office/THIRD_PARTY_NOTICES.txt"
    ).read_bytes()
    assert verify_bundle(root) == spec
    doc = yaml.safe_load((root / "compose.yaml").read_text())
    assert {
        "controller",
        "client",
        "red",
        "blue",
        "app",
        "collector",
        "indexer",
        "dashboards",
        "office",
        "network",
        "network-sensor",
        "analysis",
        "soar",
    } == set(doc["services"])
    assert all(n["internal"] for n in doc["networks"].values())
    assert "soc" not in doc["services"]["red"]["networks"]
    assert not doc["services"]["indexer"].get("ports")
    for service in doc["services"].values():
        assert not service.get("privileged")
        assert service.get("network_mode") != "host"
        assert all(port.startswith("127.0.0.1:") for port in service.get("ports", []))
    assert not (root / ".secrets").exists()
    initialize_secrets(root, spec)
    app = json.loads((root / ".secrets/app.json").read_text())
    client = json.loads((root / ".secrets/client.json").read_text())
    assert all(a["team"] == "client" for a in client["accounts"].values())
    assert len(app["accounts"]) == len(spec.actors)
    with pytest.raises(ValueError):
        initialize_secrets(root, spec)
    verify_bundle(root)
    (root / "source" / "unexpected.txt").write_text("not allowed")
    with pytest.raises(ValueError):
        verify_bundle(root)


def test_invalid_guest_network_and_resource_budget_rejected():
    data = preset_spec("windows-ad").model_dump()
    data["windows"][0]["address"] = "8.8.8.8"
    with pytest.raises(ValueError):
        LabSpec.model_validate(data)


def test_analysis_memory_and_replica_limits_must_fit_the_declared_host():
    data = preset_spec("linux-small").model_dump()
    data["analysis"]["memory_gb"] = 32
    with pytest.raises(ValueError, match="Host RAM"):
        LabSpec.model_validate(data)
    data["host_ram_gb"] = 64
    assert compose(LabSpec.model_validate(data))["services"]["analysis"]["mem_limit"] == "32g"
    data["workers_per_team"] = 16
    with pytest.raises(ValueError, match="Host RAM"):
        LabSpec.model_validate(data)
    data = preset_spec("expanded").model_dump()
    data["host_ram_gb"] = 16
    with pytest.raises(ValueError):
        LabSpec.model_validate(data)


def test_cli_requires_target_acknowledgement_before_compose(tmp_path):
    assert CliRunner().invoke(cli, ["lab", "up", "--bundle", str(tmp_path)]).exit_code != 0
    assert compose(preset_spec("expanded"))["services"]["client"]["deploy"]["replicas"] == 3
