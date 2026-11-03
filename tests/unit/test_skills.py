"""Real repository resources plus failures that must stop inference before spending quota."""

import json
import subprocess
import sys

import pytest

from saber.agents import skills
from saber.agents.llm_solver import load_skill_playbook
from saber.agents.skills import RUNTIME_SKILLS, WORLD_REFERENCE, load_playbook, skill_resources
from saber.catalog.loader import repo_root
from saber.domain.errors import IntegrationBlocked
from saber.population.agents import BlueAgent
from saber.world.agents import PLAYBOOKS, llm_messages, parse_plan
from saber.world.models import default_config
from saber.world.runtime import Runner
from saber.world.store import Store


def make_skill(root, name="soc-mon", body="Operational guidance."):
    path = root / ".claude/skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: Test skill.\n---\n{body}", encoding="utf-8")
    return path


@pytest.mark.parametrize("name", sorted(RUNTIME_SKILLS))
def test_case_playbook_includes_declared_reference_content_without_duplicates(name):
    root = repo_root()
    paths = skill_resources(name)
    assert len(paths) == len(set(paths))
    text = load_playbook(name)
    for path in paths:
        if path.name != "SKILL.md" and path != root / ".claude/skills" / WORLD_REFERENCE:
            assert path.read_text(encoding="utf-8").strip() in text
            assert (
                text.count(
                    f"--- Reference: {path.relative_to(root / '.claude/skills').as_posix()} ---"
                )
                == 1
            )
    assert "--- Reference: soc-orchestrator/reference/continuous-world.md ---" not in text
    assert len(text) <= skills.MAX_CASE_CHARS


def test_all_world_roles_load_their_skill_and_only_the_world_reference():
    assert set(PLAYBOOKS.values()) == RUNTIME_SKILLS
    for actor in default_config().actors:
        name = PLAYBOOKS[actor.team if actor.team == "client" else actor.role]
        text = load_playbook(name, mode="world")
        messages = llm_messages(actor, {"tick": 1, "events": []})
        assert messages[0]["content"].startswith(text)
        assert text.count("--- Reference:") == 1
        assert "--- Reference: soc-orchestrator/reference/continuous-world.md ---" in text
        assert len(text) <= skills.MAX_WORLD_CHARS
    assert PLAYBOOKS["access"] == "redteam-initial-access"


def test_range_playbooks_bind_the_real_executor_contract_without_world_tools():
    for name in RUNTIME_SKILLS:
        text = load_playbook(name, mode="range")
        assert "--- Reference: soc-orchestrator/reference/soc-lab.md ---" in text
        assert "--- Reference: soc-orchestrator/reference/continuous-world.md ---" not in text
        assert "HTTP 202 means queued, not applied" in text
        assert len(text) <= skills.MAX_WORLD_CHARS


def test_benchmark_specialists_use_the_same_reference_loader():
    assert load_skill_playbook("IR") == load_playbook("soc-ir")
    with pytest.raises(IntegrationBlocked, match="Unknown specialist"):
        load_skill_playbook("unknown")


def test_missing_or_broken_skill_stops_before_provider_call(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "repo_root", lambda: tmp_path)

    class NeverCalled:
        def generate(self, *args, **kwargs):
            pytest.fail("Provider must not be called with an incomplete skill")

    with pytest.raises(IntegrationBlocked, match="Missing"):
        BlueAgent(NeverCalled()).investigate("case", [], "soc-mon")
    make_skill(tmp_path, body="Read `reference/missing.md`.")
    with pytest.raises(IntegrationBlocked, match="Missing"):
        BlueAgent(NeverCalled()).investigate("case", [], "soc-mon")


def test_world_preflight_fails_before_lab_server_start(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "repo_root", lambda: tmp_path)
    store = Store(tmp_path / "world")
    try:
        with pytest.raises(IntegrationBlocked, match="Missing"):
            Runner(store, default_config(1), provider=object())
        assert store.get("meta", "world_id") is None
        assert not (store.root / "runtime.json").exists()
    finally:
        store.close()


def test_reference_cycles_are_deduplicated_and_edits_are_not_cached(tmp_path):
    path = make_skill(tmp_path, body="Read `reference/a.md`.")
    refs = path.parent / "reference"
    refs.mkdir()
    (refs / "a.md").write_text("First guidance. See `b.md`.")
    (refs / "b.md").write_text("Second guidance. See `a.md`.")
    assert load_playbook("soc-mon", root=tmp_path).count("First guidance") == 1
    (refs / "a.md").write_text("Changed guidance. See `b.md`.")
    assert "Changed guidance" in load_playbook("soc-mon", root=tmp_path)
    assert "First guidance" not in load_playbook("soc-mon", root=tmp_path)


@pytest.mark.parametrize("reference", ["../../../../private.md", "../implement-task/SKILL.md"])
def test_references_cannot_load_private_files_or_developer_skills(tmp_path, reference):
    make_skill(tmp_path, body=f"Read `{reference}`.")
    with pytest.raises(IntegrationBlocked, match="escapes|non-operational"):
        load_playbook("soc-mon", root=tmp_path)
    with pytest.raises(IntegrationBlocked, match="operational"):
        load_playbook("../soc-mon", root=tmp_path)


def test_oversize_context_fails_instead_of_truncating_required_instructions(tmp_path):
    make_skill(tmp_path, body="a" * (skills.MAX_CASE_CHARS + 1))
    with pytest.raises(IntegrationBlocked, match="exceeds"):
        load_playbook("soc-mon", root=tmp_path)


@pytest.mark.parametrize(
    "text",
    [
        "No frontmatter",
        "---\nname: wrong\ndescription: x\n---\nBody",
        "---\nname: soc-mon\ndescription: [wrong]\n---\nBody",
    ],
)
def test_malformed_skill_is_not_silently_used(tmp_path, text):
    path = make_skill(tmp_path)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(IntegrationBlocked):
        load_playbook("soc-mon", root=tmp_path)


def test_symlinked_reference_is_rejected(tmp_path):
    path = make_skill(tmp_path, body="Read `reference/link.md`.")
    refs = path.parent / "reference"
    refs.mkdir()
    (refs / "real.md").write_text("Read-only guidance.")
    try:
        (refs / "link.md").symlink_to(refs / "real.md")
    except OSError:
        pytest.skip("Creating symlinks is not enabled for this Windows user")
    with pytest.raises(IntegrationBlocked, match="Symlinked"):
        load_playbook("soc-mon", root=tmp_path)


def test_role_boundaries_still_reject_ungranted_actions():
    for actor in default_config().actors:
        actions, _ = parse_plan(
            actor, '{"actions":[{"tool":"shell","args":{}},{"tool":"read_ground_truth","args":{}}]}'
        )
        assert actions == []


def test_audit_cli_checks_the_repository_and_fails_for_missing_skills(tmp_path):
    script = repo_root() / "scripts/check_skills.py"
    output = tmp_path / "audit.json"
    good = subprocess.run(
        [sys.executable, str(script), "--out", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert good.returncode == 0, good.stderr
    report = json.loads(output.read_text())
    assert report["status"] == "PASS" and report["skill_count"] == len(RUNTIME_SKILLS) + 3
    assert report["reference_count"] == 45
    assert {r["name"] for r in report["skills"] if r["manual_only"]} == {
        "gate-review",
        "implement-task",
    }
    bad = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 1
    assert len(json.loads(bad.stdout)["errors"]) == len(RUNTIME_SKILLS)
