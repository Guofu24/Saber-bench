"""The four LLM-driven role agents. Each loads its operational skill and calls the provider once.

Safety: red/client agents return only menu action IDs, which :func:`expand_actions` validates against
the allowlist before anything is sent — an off-menu or free-form target can never reach the service.
Blue agents receive ONLY the public access log (never the server-derived truth).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from saber.agents.provider import LLMProvider
from saber.baselines.prompt import extract_answer_json
from saber.catalog.loader import repo_root
from saber.population.menus import expand_actions, menu_for

# Which skill each role loads. Red/blue are chosen per family/scenario so different scenarios
# genuinely exercise different teams ("multiple teams").
RED_SKILL = {
    "web_sqli_probe": "redteam-initial-access",
    "auth_bruteforce": "redteam-initial-access",
    "fs_change": "redteam-post-exploitation",
    "persistence": "redteam-post-exploitation",
}
BLUE_SKILL = {
    "web_sqli_probe": "soc-mon",
    "auth_bruteforce": "soc-mon",
    "fs_change": "soc-hunt",
    "persistence": "soc-hunt",
}
BLUE_TEAM = {"soc-mon": "MON", "soc-hunt": "HUNT", "soc-ir": "IR", "soc-cnt": "CNT"}


@lru_cache(maxsize=16)
def load_playbook(skill_name: str) -> str:
    """Load a skill's SKILL.md body (YAML frontmatter stripped). Empty string if absent."""
    path = repo_root() / ".claude" / "skills" / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


@dataclass
class AgentCall:
    """One agent turn: the parsed object plus provider accounting (never raises on bad output)."""

    obj: dict[str, Any] | None
    note: str
    model_id: str
    input_tokens: int
    output_tokens: int
    raw_text: str = ""


def _ask(provider: LLMProvider, system: str, user: str, *, max_tokens: int = 1024) -> AgentCall:
    resp = provider.generate(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    obj, note = extract_answer_json(resp.text)
    return AgentCall(
        obj=obj, note=note, model_id=resp.model_id,
        input_tokens=resp.input_tokens, output_tokens=resp.output_tokens, raw_text=resp.text[:400],
    )  # fmt: skip


def _menu_block(family: str, kind: str) -> str:
    return "\n".join(f"  - {a.id}: {a.label}" for a in menu_for(family, kind=kind))


@dataclass
class RedAgent:
    """Adversary emulation. Chooses inert attack actions (and benign cover) from the allowlist."""

    provider: LLMProvider
    calls: list[AgentCall] = field(default_factory=list)

    def plan(self, family: str) -> tuple[list[dict[str, str]], AgentCall]:
        skill = RED_SKILL.get(family, "redteam-initial-access")
        system = (
            load_playbook(skill)
            + "\n\n---\nYou are emulating an adversary in an isolated range. You may ONLY choose "
            "actions from the inert allowlist menu below — never invent a request. Mix a little "
            "benign cover with your attack so it does not stand out."
        )
        user = (
            f"ATTACK FAMILY: {family}\n\n"
            f"ATTACK actions available (inert):\n{_menu_block(family, 'attack')}\n\n"
            f"BENIGN cover actions available:\n{_menu_block(family, 'benign')}\n\n"
            "For a failed-login burst, set a count >= 3 to actually cross the lockout threshold.\n"
            "Return ONLY one JSON object:\n"
            '{"actions": [{"id": "<menu id>", "count": <1-10>}, ...], "goal": "<one line>"}\n'
        )
        call = _ask(self.provider, system, user)
        self.calls.append(call)
        chosen = (call.obj or {}).get("actions", []) if isinstance(call.obj, dict) else []
        plan = expand_actions(family, chosen if isinstance(chosen, list) else [])
        if not plan:  # safe fallback: run one of each attack action so the episode is not empty
            plan = expand_actions(family, [{"id": a.id, "count": 4} for a in menu_for(family, kind="attack")])
        return plan, call


@dataclass
class ClientAgent:
    """Benign user/machine population. Chooses only benign actions."""

    provider: LLMProvider
    calls: list[AgentCall] = field(default_factory=list)

    def plan(self, family: str) -> tuple[list[dict[str, str]], AgentCall]:
        system = (
            load_playbook("client-user")
            + "\n\n---\nYou are an ordinary user/machine in the range. Choose ONLY benign actions "
            "from the menu — you never attack. Pick a natural mix."
        )
        user = (
            f"SCENARIO: {family}\n\nBENIGN actions available:\n{_menu_block(family, 'benign')}\n\n"
            "Return ONLY one JSON object:\n"
            '{"actions": [{"id": "<menu id>", "count": <1-6>}, ...]}\n'
        )
        call = _ask(self.provider, system, user)
        self.calls.append(call)
        chosen = (call.obj or {}).get("actions", []) if isinstance(call.obj, dict) else []
        plan = [r for r in expand_actions(family, chosen if isinstance(chosen, list) else [])
                if r["intent"] == "benign"]  # hard guard: client traffic is benign by construction
        if not plan:
            plan = expand_actions(family, [{"id": a.id, "count": 2} for a in menu_for(family, kind="benign")])
        return plan, call


@dataclass
class BlueAgent:
    """Defender. Reads the real access log and reports which line-ids are malicious."""

    provider: LLMProvider
    calls: list[AgentCall] = field(default_factory=list)

    def investigate(
        self, scenario: str, log_lines: list[str], skill: str
    ) -> tuple[dict[str, Any], AgentCall]:
        system = (
            load_playbook(skill)
            + "\n\n---\nYou are working ONE live case. Decide which access-log lines are malicious, "
            "from the evidence only. Output the machine answer, no narration."
        )
        numbered = "\n".join(f"line-{i}: {ln}" for i, ln in enumerate(log_lines))
        user = (
            f"SCENARIO: {scenario}\n\nACCESS LOG (one real request per line):\n{numbered}\n\n"
            "Report the malicious lines. Return ONLY one JSON object:\n"
            '{"malicious_line_ids": ["line-<n>", ...], "verdict": "attack|benign", '
            '"summary": "<one line>"}\n'
        )
        call = _ask(self.provider, system, user, max_tokens=1536)
        self.calls.append(call)
        obj = call.obj if isinstance(call.obj, dict) else {}
        ids = obj.get("malicious_line_ids", [])
        findings = {
            "malicious_line_ids": sorted({str(x) for x in ids}) if isinstance(ids, list) else [],
            "verdict": str(obj.get("verdict", "")),
            "summary": str(obj.get("summary", ""))[:200],
        }
        return findings, call


@dataclass
class Orchestrator:
    """SOC lead. Routes the case to a blue team and records severity/status."""

    provider: LLMProvider
    calls: list[AgentCall] = field(default_factory=list)

    def route(self, scenario: str, n_requests: int) -> tuple[str, AgentCall]:
        """Pick the blue team. Validated against the real teams; falls back to the scenario default."""
        default_skill = BLUE_SKILL.get(scenario, "soc-mon")
        system = (
            load_playbook("soc-orchestrator")
            + "\n\n---\nRoute this incoming signal to ONE blue team. Output the machine answer only."
        )
        user = (
            f"Incoming signal from scenario '{scenario}' with {n_requests} requests observed.\n"
            "Teams: MON (24/7 monitoring/triage), HUNT (threat hunting), IR (incident response), "
            "CNT (detection content).\n"
            'Return ONLY: {"team": "MON|HUNT|IR|CNT", "severity": "low|medium|high|critical", '
            '"reason": "<one line>"}\n'
        )
        call = _ask(self.provider, system, user)
        self.calls.append(call)
        obj = call.obj if isinstance(call.obj, dict) else {}
        team = str(obj.get("team", "")).upper()
        skill = next((s for s, t in BLUE_TEAM.items() if t == team), default_skill)
        return skill, call
