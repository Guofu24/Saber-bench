import hashlib

import pytest

from saber.agents.skill_library import (
    MAX_REFERENCE_CHARS,
    guidance_prompt,
    load_reference_library,
    validate_library,
)
from saber.domain.errors import IntegrationBlocked


def item(text):
    return {
        "title": "Acquisition",
        "text": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def test_library_reads_only_declared_owned_documents_and_not_contracts(tmp_path):
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
