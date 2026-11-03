import json

from saber.agents.provider import LLMResponse
from saber.lab.capabilities import allowed, planner_allowed
from saber.lab.controller import Controller
from saber.lab.learning import messages
from saber.world import learning


def test_range_consults_locally_and_next_provider_prompt_contains_pinned_guide(
    lab, tmp_path, monkeypatch
):
    spec, creds, *_ = lab
    actor = next(a for a in spec.actors if a.role == "dfir")

    class ConsultProvider:
        def __init__(self):
            self.prompts = []

        def generate_for(self, team, prompt, **kwargs):
            self.prompts.append(prompt)
            return LLMResponse(
                text=json.dumps({"tool": "consult_skill", "args": {"topic": "memory-malware"}}),
                model_id="fixture",
                input_tokens=0,
                output_tokens=0,
            )

    def collector_only(url, **kwargs):
        assert url == "http://collector/cases", "Guidance must not dispatch to a worker"
        return 200, {"cases": []}

    monkeypatch.setattr("saber.lab.controller.request", collector_only)
    provider = ConsultProvider()
    root = tmp_path / "control"
    controller = Controller(spec, root, creds["controller"], {}, "http://collector", provider)
    try:
        controller.actor_step(actor, 1)
        pin = learning.prompt_version(controller.store, "soc-dfir")
        assert pin
        guide = pin["references"]["memory-malware"]["text"]
        assert guide not in provider.prompts[0][0]["content"]
        result = controller.store.get("lab-memory", actor.id)["result"]
        assert result["status"] == 200 and result["guidance_only"]
        assert "pid" not in result and "execution_evidence" not in result
        assert next(iter(controller.store.items("lab-jobs").values()))["status"] == "COMPLETED"
        assert controller.store.get("lab-office", actor.id)[-1]["evidence_complete"]
        controller.actor_step(actor, 2)
        assert guide in provider.prompts[1][0]["content"]
    finally:
        controller.close()
    restarted = Controller(spec, root, creds["controller"], {}, "http://collector")
    try:
        retained = learning.prompt_version(restarted.store, "soc-dfir")
        assert retained == pin
        assert guide in messages(actor, restarted.observe(actor), retained, [])[0]["content"]
        assert "consult_skill" not in allowed("blue", "dfir")
        assert "consult_skill" in planner_allowed("blue", "dfir")
        assert "consult_skill" not in planner_allowed("red", "recon")
    finally:
        restarted.close()
