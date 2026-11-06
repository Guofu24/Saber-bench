import hashlib

import pytest

from saber.agents.skill_library import (
    MAX_REFERENCE_CHARS,
    guidance_prompt,
    load_reference_library,
    validate_library,
)
from saber.agents.skills import load_playbook, skill_resources
from saber.domain.errors import IntegrationBlocked


def item(text):
    return {
        "title": "Acquisition",
        "text": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def test_library_reads_only_declared_documents(tmp_path):
    folder = tmp_path / ".claude/skills/soc-dfir"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: soc-dfir\ndescription: Test.\n---\nRead `guide.md`.\n", encoding="utf-8"
    )
    (folder / "guide.md").write_text("# Evidence\nPreserve the original.", encoding="utf-8")
    (folder / "unlinked.md").write_text("Do not export this file.", encoding="utf-8")
    lib = load_reference_library("soc-dfir", root=tmp_path)
    assert set(lib) == {"guide"}
    assert lib["guide"]["text"].endswith("Preserve the original.")
    (folder / "guide.md").write_text("x" * (MAX_REFERENCE_CHARS + 1), encoding="utf-8")
    with pytest.raises(IntegrationBlocked, match="limit"):
        load_reference_library("soc-dfir", root=tmp_path)


def test_shared_topics_are_namespaced_and_cross_team_guidance_is_excluded(tmp_path):
    base = tmp_path / ".claude/skills"
    for name in ("soc-dfir", "soc-ir", "client-user", "soc-orchestrator"):
        (base / name).mkdir(parents=True)
    (base / "soc-dfir/SKILL.md").write_text(
        "---\nname: soc-dfir\ndescription: Test.\n---\n"
        "Read `guide.md`, `../soc-ir/guide.md`, `../client-user/guide.md` and "
        "`../soc-orchestrator/reference/continuous-world.md`.\n",
        encoding="utf-8",
    )
    for name in ("soc-dfir", "soc-ir", "client-user"):
        (base / name / "guide.md").write_text(f"# {name}\nContent for {name}.", encoding="utf-8")
    contract = base / "soc-orchestrator/reference/continuous-world.md"
    contract.parent.mkdir()
    contract.write_text("# Contract\nNot a selectable topic.", encoding="utf-8")
    library = load_reference_library("soc-dfir", root=tmp_path)
    assert set(library) == {"guide", "soc-ir--guide"}
    assert library["guide"]["text"] != library["soc-ir--guide"]["text"]
    (base / "client-user/SKILL.md").write_text(
        "---\nname: client-user\ndescription: Test.\n---\nRead `../soc-ir/guide.md`.\n",
        encoding="utf-8",
    )
    assert load_reference_library("client-user", root=tmp_path) == {}


def test_selected_text_comes_from_pinned_library_not_untrusted_observation():
    pin = {"id": "version-one", "references": {"acquisition": item("Preserve original bytes.")}}
    forged = {"version": "version-one", "topic": "acquisition", "text": "UNTRUSTED OVERRIDE"}
    text = guidance_prompt(pin, forged)
    assert "Preserve original bytes." in text and "UNTRUSTED OVERRIDE" not in text
    for selection in (
        {"version": "older-version", "topic": "acquisition"},
        {"version": "version-one", "topic": "../../private"},
        {"version": "version-one", "topic": []},
    ):
        assert "Preserve original bytes." not in guidance_prompt(pin, selection)
    assert guidance_prompt({"base": "Legacy version without references"}) == ""
    pin["references"]["acquisition"]["text"] = "changed without a new hash"
    with pytest.raises(ValueError, match="Corrupt"):
        guidance_prompt(pin, forged)


@pytest.mark.parametrize("value", [[], {"../escape": item("x")}, {"valid": {"text": "x"}}])
def test_malformed_reference_library_is_rejected(value):
    with pytest.raises(ValueError):
        validate_library(value)


def test_optional_library_guides_are_pinned_and_exported_without_inflating_case(tmp_path):
    folder = tmp_path / ".claude/skills/soc-dfir"
    folder.mkdir(parents=True)
    entry = folder / "SKILL.md"
    entry.write_text(
        "---\nname: soc-dfir\ndescription: Test.\nmetadata:\n"
        "  saber-library: [practice.md]\n---\nCore instructions. Read `required.md`.\n",
        encoding="utf-8",
    )
    (folder / "required.md").write_text("# Required\nCase contract.", encoding="utf-8")
    guide = folder / "practice.md"
    guide.write_text("# Practice\nOptional training method.", encoding="utf-8")
    assert guide in skill_resources("soc-dfir", root=tmp_path)
    assert guide not in skill_resources("soc-dfir", root=tmp_path, include_library=False)
    case = load_playbook("soc-dfir", root=tmp_path)
    assert "Case contract." in case and "Optional training method." not in case
    lib = load_reference_library("soc-dfir", root=tmp_path)
    assert lib["practice"]["text"].endswith("Optional training method.")
    guide.unlink()
    with pytest.raises(IntegrationBlocked, match="Missing"):
        load_reference_library("soc-dfir", root=tmp_path)


@pytest.mark.parametrize("reference", ["../../private.md", "../implement-task/SKILL.md"])
def test_optional_references_cannot_escape_operational_skills(tmp_path, reference):
    folder = tmp_path / ".claude/skills/soc-dfir"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: soc-dfir\ndescription: Test.\nmetadata:\n"
        f"  saber-library: [{reference}]\n---\nCore instructions.\n",
        encoding="utf-8",
    )
    with pytest.raises(IntegrationBlocked, match="escapes|non-operational"):
        load_reference_library("soc-dfir", root=tmp_path)


@pytest.mark.parametrize("metadata", ["[]", "{saber-library: text}", "{saber-library: [42]}"])
def test_invalid_optional_metadata_fails_closed(tmp_path, metadata):
    folder = tmp_path / ".claude/skills/soc-dfir"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: soc-dfir\ndescription: Test.\nmetadata: {metadata}\n---\nCore.\n",
        encoding="utf-8",
    )
    with pytest.raises(IntegrationBlocked, match="Invalid"):
        load_reference_library("soc-dfir", root=tmp_path)
