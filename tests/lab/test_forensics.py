import json

from saber.agents.provider import LLMResponse
from saber.forensics.vault import Vault
from saber.lab.capabilities import allowed, configured_tools
from saber.lab.controller import Controller
from saber.lab.office import publish_actor


def test_provider_driven_investigation_resumes_without_worker_dispatch(lab, tmp_path, monkeypatch):
    spec, creds, *_ = lab
    actor = next(a for a in spec.actors if a.role == "dfir")
    root = tmp_path / "control"
    source = tmp_path / "events.csv"
    source.write_text("UtcTime,Computer,Image\n2026-11-03T10:00:00,pc-a,worker.exe\n")
    with Vault(root) as vault:
        vault.import_file(source, "csv", "Fixture")

    class Provider:
        def __init__(self):
            self.calls = 0

        def generate_for(self, team, prompt, **kwargs):
            assert team == "blue"
            assert "forensic_query" in prompt[0]["content"]
            obs = json.loads(prompt[1]["content"])["observation"]
            previous = obs.get("result", {}).get("forensics", {})
            stage = self.calls
            self.calls += 1
            if stage == 0:
                tool, args = "forensic_sources", {}
            elif stage == 1:
                tool, args = (
                    "forensic_open",
                    {
                        "source_ids": [previous["sources"][0]["id"]],
                        "question": "Check response gaps",
                    },
                )
            elif stage == 2:
                tool, args = "forensic_query", {"session_id": previous["id"], "mode": "timeline"}
            elif stage == 3:
                tool, args = (
                    "response_review",
                    {
                        "session_id": previous["session_id"],
                        "residual_risk": "No evidence of containment",
                    },
                )
            else:
                tool, args = (
                    "forensic_finish",
                    {
                        "session_id": previous["session_id"],
                        "disposition": "partial",
                        "summary": "Need response evidence",
                    },
                )
            return LLMResponse(
                text=json.dumps({"tool": tool, "args": args}),
                model_id="offline-fixture",
                input_tokens=0,
                output_tokens=0,
            )

    def collector_only(url, **kwargs):
        assert url == "http://collector/cases"
        return 200, {"cases": []}

    monkeypatch.setattr("saber.lab.controller.request", collector_only)
    provider = Provider()
    controller = Controller(spec, root, creds["controller"], {}, "http://collector", provider)
    try:
        for tick in range(1, 4):
            controller.actor_step(actor, tick)
        checkpoint = controller.store.get("lab-memory", actor.id)["result"]
        assert checkpoint["forensics"]["evidence"]
        assert "pid" not in checkpoint
    finally:
        controller.close()
    resumed = Controller(spec, root, creds["controller"], {}, "http://collector", provider)
    try:
        assert resumed.observe(actor)["forensics"]["sessions"]
        resumed.actor_step(actor, 4)
        resumed.actor_step(actor, 5)
        result = resumed.store.get("lab-memory", actor.id)["result"]
        assert result["forensics"]["state"] == "PARTIAL"
        assert provider.calls == 5
        assert all(j["status"] == "COMPLETED" for j in resumed.store.items("lab-jobs").values())
        assert "forensic_query" not in allowed(actor.team, actor.role)
        assert "forensic_query" in configured_tools(actor, spec)

        def no_remote_proof(*args, **kwargs):
            raise AssertionError("Local analysis has no remote PID proof")

        monkeypatch.setattr("saber.lab.office.request", no_remote_proof)
        publish_actor(resumed.store, actor, "unused", "unused", "unused", "unused")
        page = json.loads((root / "range-office" / (actor.id + ".json")).read_text())
        assert all(e["result"]["analysis_only"] for e in page["entries"])
        assert all(not e["evidence_complete"] and e["evidence"] == [] for e in page["entries"])
        assert page["entries"][-1]["result"]["forensics"]["state"] == "PARTIAL"
    finally:
        resumed.close()
