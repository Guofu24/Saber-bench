import json

import pytest
import yaml

from saber.environments.bundle import compose_config, render_bundle, verify_bundle
from saber.environments.models import EnvironmentConfig


@pytest.mark.parametrize("profile", ["local", "sandbox", "vm", "remote"])
def test_bundle_is_portable_and_contains_only_allowlisted_inputs(tmp_path, profile):
    root = tmp_path / "repo"
    (root / "src/saber").mkdir(parents=True)
    (root / "src/saber/__init__.py").write_text("")
    (root / "catalog").mkdir()
    (root / "catalog/subtasks.json").write_text("{}")
    (root / "pyproject.toml").write_text("")
    (root / "uv.lock").write_text("")
    for name in ("keys_pool.txt", ".env", "private.txt"):
        (root / name).write_text("DO-NOT-EXPORT")
    config = EnvironmentConfig(name="example", profile=profile)
    out = tmp_path / "bundle"
    render_bundle(config, out, source_root=root)
    assert verify_bundle(out) == config
    assert not any(b"DO-NOT-EXPORT" in p.read_bytes() for p in out.rglob("*") if p.is_file())
    assert (out / "compose.yaml").exists() == (profile == "sandbox")
    with pytest.raises(ValueError, match="already exists"):
        render_bundle(config, out, source_root=root)


def test_sandbox_defaults_are_isolated_and_gemini_is_explicit():
    config = EnvironmentConfig(name="example", profile="sandbox")
    plain = compose_config(config, "test")
    worker = plain["services"]["world"]
    assert worker["network_mode"] == "none" and "ports" not in worker
    assert worker["user"] != "root" and worker["read_only"]
    assert worker["cap_drop"] == ["ALL"] and "privileged" not in worker
    assert worker["mem_limit"] == "2048m" and worker["pids_limit"] == 256
    assert "secrets" not in plain
    live = compose_config(config, "test", llm=True)
    assert "network_mode" not in live["services"]["world"]
    assert live["secrets"]["gemini-pool"]["file"].startswith("${SABER_ENV_KEY_POOL:?")


def test_tampered_bundle_and_forged_privileged_compose_are_rejected(tmp_path):
    config = EnvironmentConfig(name="example", profile="sandbox")
    render_bundle(config, tmp_path / "bundle")
    root = tmp_path / "bundle"
    path = root / "compose.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["services"]["world"]["privileged"] = True
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ValueError, match="changed"):
        verify_bundle(root)
    import hashlib

    manifest_path = root / "bundle-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["compose.yaml"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="supported sandbox"):
        verify_bundle(root)
