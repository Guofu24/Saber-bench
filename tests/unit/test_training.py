"""Training integrity/lineage and review boundaries, including actual CLI and world use."""

import json

import pytest
from click.testing import CliRunner

from saber.agents.skill_library import load_reference_library
from saber.cli.main import cli
from saber.forensics.vault import Vault
from saber.training.catalog import TRACKS
from saber.training.practice import MAX_JSON_BYTES, attach, digest, initialize, report
from saber.world.agents import PLAYBOOKS, action, llm_messages
from saber.world.learning import prompt_version
from saber.world.models import BLUE_ROLES, WorldConfig
from saber.world.runtime import Runner
from saber.world.store import Store


@pytest.fixture
def practice(tmp_path):
    root = tmp_path / "practice"
    manifest = initialize(root, "blue-dfir", "local-example", synthetic=True)
    original = tmp_path / "access.log"
    original.write_text(
        '192.0.2.8 - - [05/Nov/2026:10:00:00 +0000] "GET /portal HTTP/1.1" 200 23\n',
        encoding="utf-8",
    )
    result = attach(
        root, original, "apache", "Synthetic access", "Locally authored", "Original bytes"
    )
    return root, manifest, original, result["source"]


def review_file(root, manifest, **changes):
    value = {
        "schema_version": 1,
        "run_id": manifest.run_id,
        "manifest_sha256": digest(manifest),
        "reviewer": "Local test reviewer",
        "criteria": [
            {
                "criterion": "timeline",
                "verdict": "supported",
                "rationale": "The cited record has a timestamp.",
                "evidence_ids": [1],
            }
        ],
    }
    value.update(changes)
    path = root / "review.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_tracks_cover_operational_roles_and_references_without_claiming_htb_execution():
    assert len(TRACKS) == 9
    assert set(BLUE_ROLES) <= {r for t in TRACKS.values() if t.team == "blue" for r in t.roles}
    for selected in TRACKS.values():
        ids = [c.id for c in selected.criteria]
        assert len(ids) == len(set(ids))
        for role in selected.roles:
            library = load_reference_library(PLAYBOOKS[role])
            assert selected.guidance_for(role) in library
    assert not any(k.endswith("external-practice") for k in load_reference_library("client-user"))
    assert "soc-orchestrator--external-practice" not in load_reference_library(
        "redteam-initial-access"
    )


def test_cli_initialization_is_offline_and_cannot_overwrite(tmp_path, monkeypatch):
    import socket

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("No network"))
    runner = CliRunner()
    root = tmp_path / "practice"
    args = ["training", "init", "--track", "red-web", "--exercise", "local-web", "--out", str(root)]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    manifest = json.loads(result.output)
    assert manifest["live_execution"] is manifest["benchmark_ready"] is False
    assert (root / "brief.md").is_file() and not (root / "world").exists()
    assert runner.invoke(cli, args).exit_code != 0
    bad = runner.invoke(cli, ["training", "prepare-world", "--run", str(root)])
    assert bad.exit_code != 0  # red tracks never become an implicit external executor


@pytest.mark.parametrize(
    "url",
    [
        "https://hackthebox.com.evil.example/lab",
        "https://evil.example/hackthebox.com",
        "http://hackthebox.com/lab",
        "https://hackthebox.com/lab?session=private",
        "https://user@hackthebox.com/lab",
        "https://hackthebox.com/#private",
        "file:///data",
    ],
)
def test_reference_urls_cannot_smuggle_credentials_or_external_targets(tmp_path, url):
    with pytest.raises(ValueError):
        initialize(tmp_path / "bad", "blue-dfir", "sample", url)
    assert not (tmp_path / "bad").exists()


def test_import_preserves_original_and_report_does_not_grade_integrity_as_correctness(practice):
    root, manifest, original, source = practice
    with Vault(root / "world") as vault:
        assert original.read_bytes() == vault.original(source["id"]).read_bytes()
    before = report(root)
    assert before["status"] == "AWAITING_REVIEW"
    assert before["origin"] == "synthetic"
    assert before["sources"][0]["integrity_verified"]
    reviewed = report(root, review_file(root, manifest))
    assert reviewed["status"] == "REVIEW_INCOMPLETE"
    assert reviewed["verified_citations"]["1"]["source_id"] == source["id"]
    assert reviewed["semantic_verification"] is reviewed["benchmark_ready"] is False
    assert reviewed["verdict_counts"]["supported"] == 1


def test_source_tampering_and_forged_record_hash_fail_integrity(practice):
    root, manifest, _, source = practice
    review = review_file(root, manifest)
    with Vault(root / "world") as vault:
        vault.db.execute("UPDATE records SET sha256=? WHERE id=1", ("f" * 64,))
        vault.db.commit()
    result = report(root, review)
    assert result["status"] == "INTEGRITY_FAILURE"
    assert "Record integrity mismatch: 1" in result["issues"]
    with Vault(root / "world") as vault:
        vault.original(source["id"]).write_bytes(b"changed")
    assert report(root)["status"] == "INTEGRITY_FAILURE"


def test_foreign_evidence_and_modified_manifest_are_rejected(practice, tmp_path):
    root, manifest, _, _ = practice
    unrelated = tmp_path / "unregistered.log"
    unrelated.write_text("Unrelated source", encoding="utf-8")
    with Vault(root / "world") as vault:
        vault.import_file(unrelated, "text", "Not registered to this exercise")
    path = review_file(
        root,
        manifest,
        criteria=[
            {
                "criterion": "timeline",
                "verdict": "supported",
                "rationale": "Incorrect citation",
                "evidence_ids": [2],
            }
        ],
    )
    assert report(root, path)["status"] == "INTEGRITY_FAILURE"
    data = json.loads((root / "practice.json").read_text())
    data["assisted"] = True
    (root / "practice.json").write_text(json.dumps(data))
    assert report(root)["status"] == "INTEGRITY_FAILURE"
    with pytest.raises(ValueError, match="another manifest"):
        report(root, path)


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewer": " "},
        {"run_id": "a" * 32},
        {
            "criteria": [
                {"criterion": "invented", "verdict": "inconclusive", "rationale": "Missing"}
            ]
        },
        {"criteria": [{"criterion": "scope", "verdict": "supported", "rationale": "No citation"}]},
        {"criteria": [{"criterion": "scope"}, {"criterion": "scope"}]},
    ],
)
def test_unattributed_unbound_or_uncited_reviews_are_not_accepted(practice, changes):
    root, manifest, _, _ = practice
    with pytest.raises(ValueError):
        report(root, review_file(root, manifest, **changes))


def test_complete_inconclusive_review_is_recorded_without_certifying_success(practice):
    root, manifest, _, _ = practice
    path = review_file(
        root,
        manifest,
        criteria=[
            {
                "criterion": c.id,
                "verdict": "inconclusive",
                "rationale": "Insufficient evidence for this criterion.",
            }
            for c in manifest.track.criteria
        ],
    )
    result = report(root, path)
    assert result["status"] == "REVIEW_RECORDED"
    assert result["verdict_counts"] == {"inconclusive": len(manifest.track.criteria)}
    assert not result["semantic_verification"]


def test_partial_parse_and_unknown_timezone_remain_visible(practice, tmp_path):
    root, _, _, _ = practice
    raw = tmp_path / "partial.csv"
    raw.write_bytes(b"Timestamp,Computer\n2026-11-05T10:00:00,host-a\n\xff")
    attach(
        root, raw, "csv", "Partial conversion", "Synthetic", "Deliberate parser-negative fixture"
    )
    result = report(root)
    partial = next(s for s in result["sources"] if s["warnings"].get("parse_stopped"))
    assert partial["integrity_verified"] and not partial["indexed_complete"]
    assert partial["warnings"]["unknown_timestamp"] == 1


def test_failed_attachment_leaves_a_visible_incomplete_receipt(practice, tmp_path):
    root, _, _, _ = practice
    with pytest.raises(ValueError):
        attach(root, tmp_path / "missing", "text", "Missing", "Synthetic", "Original bytes")
    assert report(root)["status"] == "INTEGRITY_FAILURE"


def test_oversized_review_and_cli_report_overwrite_are_rejected(practice):
    root, _, _, _ = practice
    bad = root / "large.json"
    bad.write_bytes(b" " * (MAX_JSON_BYTES + 1))
    with pytest.raises(ValueError, match="128 KiB"):
        report(root, bad)
    out = root / "report.json"
    runner = CliRunner()
    args = ["training", "report", "--run", str(root), "--out", str(out)]
    assert runner.invoke(cli, args).exit_code == 0
    original = out.read_bytes()
    assert runner.invoke(cli, args).exit_code != 0
    assert out.read_bytes() == original


def test_prepared_world_reads_new_guidance_and_imported_evidence_through_real_http(practice):
    root, _, _, source = practice
    result = CliRunner().invoke(cli, ["training", "prepare-world", "--run", str(root)])
    assert result.exit_code == 0, result.output
    config = WorldConfig.model_validate_json((root / "world/config.json").read_text())
    assert all(a.team == "blue" for a in config.actors) and not config.learning_enabled
    store = Store(root / "world")
    runner = Runner(store, config)
    try:
        client = runner.clients["blue-dfir"]
        topic = "soc-orchestrator--external-practice"
        selected = client.act(action("consult_skill", topic=topic))
        assert selected["status"] == 200
        pin = prompt_version(store, "soc-dfir")
        assert "Historical" in runner.world.actors["blue-dfir"].goal
        assert (
            pin["references"][topic]["text"]
            in llm_messages(runner.world.actors["blue-dfir"], client.observe(), pinned=pin)[0][
                "content"
            ]
        )
        opened = client.act(
            action(
                "forensic_open", source_ids=[source["id"]], question="What does the request prove?"
            )
        )
        found = client.act(
            action("forensic_query", session_id=opened["forensics"]["id"], text="/portal")
        )
        assert found["forensics"]["evidence"][0]["id"] == 1
        # The review and metadata are not filesystem-readable agent tools.
        assert (
            client.act(action("read_file", path=str(root / "review-template.json")))["status"]
            == 403
        )
    finally:
        runner.close()
        store.close()
    assert CliRunner().invoke(cli, ["training", "prepare-world", "--run", str(root)]).exit_code != 0
