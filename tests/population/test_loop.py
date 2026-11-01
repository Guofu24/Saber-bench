"""End-to-end population loop over the REAL range, driven by a scripted (offline) provider — no
Gemini, no spend. Proves red/client/orchestrator/blue plumbing and the server-side scoring run."""

from __future__ import annotations

import json

from saber.agents.provider import LLMResponse
from saber.population.agents import load_playbook
from saber.population.loop import run_population_episode
from saber.population.menus import menu_for
from saber.range.live.controlplane import _is_sqli_target


class ScriptedProvider:
    """Returns role-appropriate JSON by inspecting the prompt. Blue mirrors the server-side SQLi
    rule so the loop reaches a gradeable (here, perfect) detection — this exercises scoring, not
    model skill."""

    model = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    @property
    def model_id(self) -> str:
        return self.model

    def generate(self, messages, *, tools=None, max_tokens=1024) -> LLMResponse:
        self.calls += 1
        user = messages[-1]["content"]
        if "ACCESS LOG" in user:  # blue
            ids = []
            for line in user.splitlines():
                if not line.startswith("line-"):
                    continue
                tag, _, rest = line.partition(": ")
                try:
                    rec = json.loads(rest)
                except json.JSONDecodeError:
                    continue
                if _is_sqli_target(str(rec.get("target", ""))):
                    ids.append(tag)
            text = json.dumps({"malicious_line_ids": ids, "verdict": "attack", "summary": "sqli"})
        elif "Route this incoming signal" in user:  # orchestrator
            text = json.dumps({"team": "MON", "severity": "high", "reason": "web attack"})
        elif "ATTACK FAMILY" in user:  # red
            atk = [{"id": a.id, "count": 1} for a in menu_for("web_sqli_probe", kind="attack")]
            text = json.dumps({"actions": atk, "goal": "probe the search endpoint"})
        else:  # client
            ben = [{"id": a.id, "count": 2} for a in menu_for("web_sqli_probe", kind="benign")[:3]]
            text = json.dumps({"actions": ben})
        return LLMResponse(text=text, model_id=self.model, input_tokens=20, output_tokens=10)


def test_population_episode_runs_and_scores(tmp_path) -> None:
    prov = ScriptedProvider()
    ep = run_population_episode("web_sqli_probe", 1, prov, workdir=tmp_path)

    assert ep.llm_calls == 4  # red + client + orchestrator + blue
    assert ep.requests_sent > 0
    assert ep.all_targets_on_menu is True  # safety invariant held
    assert ep.truth_malicious > 0  # the real range flagged the inert probes server-side
    assert ep.blue_team == "MON"
    # Scripted blue mirrors the server rule, so detection is perfect here.
    assert ep.f1 == 1.0 and ep.blue_fp == 0 and ep.blue_fn == 0
    # A case record was written to the evidence dir.
    case_path = tmp_path / "web_sqli_probe" / "seed-1" / "case.json"
    assert case_path.exists()
    assert json.loads(case_path.read_text())["assigned_team"] == "MON"


def test_blue_playbook_is_the_mon_skill() -> None:
    assert "SOC" in load_playbook("soc-mon") or "giám sát" in load_playbook("soc-mon")
    assert load_playbook("redteam-initial-access")  # red skill loads too


def test_multi_client_and_multi_blue_scales_calls(tmp_path) -> None:
    ep = run_population_episode(
        "web_sqli_probe",
        1,
        ScriptedProvider(),
        workdir=tmp_path,
        n_clients=2,
        blue_teams=["MON", "HUNT"],
    )
    assert ep.llm_calls == 6  # 2 clients + red + orchestrator + 2 blue teams
    assert ep.n_clients == 2
    assert ep.blue_team == "MON+HUNT"
    assert len(ep.case["per_team"]) == 2
    assert {t["team"] for t in ep.case["per_team"]} == {"MON", "HUNT"}
    assert ep.all_targets_on_menu is True


def test_run_forever_honors_preexisting_stop_file(tmp_path) -> None:
    from saber.population.loop import run_forever

    stopf = tmp_path / "STOP"
    stopf.write_text("x")
    waited: list[str] = []
    rep = run_forever(
        ["web_sqli_probe"],
        ScriptedProvider(),
        workdir=tmp_path / "w",
        stop_file=stopf,
        interval_s=0,
        on_wait=waited.append,
    )
    assert rep.episodes == []  # stop file present from the start -> no rounds run
    assert any("stop file" in m for m in waited)


def test_run_forever_runs_rounds_then_stops(tmp_path) -> None:
    from saber.population.loop import run_forever

    stopf = tmp_path / "STOP2"

    def on_ep(ep, i) -> None:
        if i >= 1:  # after the 2nd episode, ask it to stop
            stopf.write_text("x")

    rep = run_forever(
        ["web_sqli_probe", "auth_bruteforce"],
        ScriptedProvider(),
        workdir=tmp_path / "w2",
        stop_file=stopf,
        interval_s=0,
        on_episode=on_ep,
    )
    assert len(rep.episodes) == 2  # ran rounds 0 and 1, then the stop file halted it
