import json

import pytest
import yaml

from saber.agents.skills import RUNTIME_SKILLS, WORLD_REFERENCE, load_playbook, skill_resources
from saber.catalog.loader import repo_root
from saber.domain.errors import IntegrationBlocked
from saber.environments.bundle import OFFICE_FILES, compose_config, render_bundle, verify_bundle
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
    (root / "LICENSE").write_text("Synthetic license notice for export verification.")
    for name in RUNTIME_SKILLS:
        skill = root / ".claude/skills" / name / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(
            f"---\nname: {name}\ndescription: Test.\n---\nRead `reference/public.md`.\n"
        )
        (skill.parent / "reference").mkdir()
        (skill.parent / "reference/public.md").write_text("Public reference guidance.")
        (skill.parent / "reference/private.md").write_text("DO-NOT-EXPORT")
    for name in OFFICE_FILES:
        path = root / "agent-office" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public viewer")
    (root / "agent-office/private.js").write_text("DO-NOT-EXPORT")
    (root / "agent-office/node_modules").mkdir()
    (root / "agent-office/node_modules/private.txt").write_text("DO-NOT-EXPORT")
    for name in ("keys_pool.txt", ".env", "private.txt"):
        (root / name).write_text("DO-NOT-EXPORT")
    config = EnvironmentConfig(name="example", profile=profile)
    out = tmp_path / "bundle"
    render_bundle(config, out, source_root=root)
    assert verify_bundle(out) == config
    assert not any(b"DO-NOT-EXPORT" in p.read_bytes() for p in out.rglob("*") if p.is_file())
    assert (out / "compose.yaml").exists() == (profile == "sandbox")
    assert (out / "agent-office/viewer/index.html").read_text() == "public viewer"
    assert not (out / "source/agent-office").exists()
    assert (out / "source/.claude/skills/soc-ir/reference/public.md").is_file()
    assert (out / "source/LICENSE").read_bytes() == (root / "LICENSE").read_bytes()
    assert (out / "agent-office/LICENSE").read_bytes() == (
        root / "agent-office/LICENSE"
    ).read_bytes()
    assert (out / "agent-office/THIRD_PARTY_NOTICES.txt").read_bytes() == (
        root / "agent-office/THIRD_PARTY_NOTICES.txt"
    ).read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        render_bundle(config, out, source_root=root)


def test_exported_playbooks_match_checkout_including_transitive_references(tmp_path):
    root = repo_root()
    out = tmp_path / "bundle"
    render_bundle(EnvironmentConfig(name="skills-check", profile="sandbox"), out)
    verify_bundle(out)
    for name in RUNTIME_SKILLS:
        for resource in skill_resources(name):
            exported = out / "source" / resource.relative_to(root)
            assert exported.read_bytes() == resource.read_bytes()
        assert load_playbook(name, root=out / "source") == load_playbook(name)
        assert load_playbook(name, mode="world", root=out / "source") == load_playbook(
            name, mode="world"
        )
    assert (out / "source/.claude/skills" / WORLD_REFERENCE).is_file()


def test_missing_required_skill_refuses_export(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from saber.cli.main import cli
    from saber.environments import bundle

    def missing(*args, **kwargs):
        raise IntegrationBlocked("Missing required skill.")

    monkeypatch.setattr(bundle, "skill_resources", missing)
    out = tmp_path / "bundle"
    with pytest.raises(IntegrationBlocked, match="Missing required skill"):
        render_bundle(EnvironmentConfig(name="missing", profile="sandbox"), out)
    assert not out.exists()
    config = tmp_path / "profile.json"
    config.write_text(EnvironmentConfig(name="missing", profile="sandbox").model_dump_json())
    result = CliRunner().invoke(cli, ["env", "render", "--config", str(config), "--out", str(out)])
    assert result.exit_code == 1
    assert "Error: Missing required skill." in result.output
    assert not out.exists()


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


def test_extra_build_context_file_is_not_silently_baked_into_image(tmp_path):
    root = tmp_path / "bundle"
    render_bundle(EnvironmentConfig(name="example", profile="sandbox"), root)
    (root / "source/private.txt").write_text("private-not-for-image")
    with pytest.raises(ValueError, match="Untracked build-context"):
        verify_bundle(root)
