from __future__ import annotations

import pytest
from pydantic import ValidationError

from saber.agents.skills import load_playbook
from saber.agents.specialties import BLUE_SKILLS, DEFAULT_BLUE_ROLES
from saber.world.agents import PLAYBOOKS, llm_messages
from saber.world.models import Actor, default_config, specialties_for, tools_for


def test_default_roster_is_compatible_but_all_specialists_can_be_configured():
    assert [a.role for a in default_config().actors if a.team == "blue"] == list(DEFAULT_BLUE_ROLES)
    assert len(BLUE_SKILLS) == 12
    for role, skill in BLUE_SKILLS.items():
        actor = Actor(id=f"blue-{role}", team="blue", role=role)
        assert PLAYBOOKS[role] == skill
        assert {"query_events", "get_evidence", "record_finding"} <= tools_for(actor)
        assert llm_messages(actor, {})[0]["content"].startswith(load_playbook(skill, mode="world"))


def test_secondary_specialty_is_operator_granted_not_requested_by_observation():
    actor = Actor(id="analyst", team="blue", role="dfir", specialties=("network", "malware"))
    assert specialties_for(actor) == ("dfir", "network", "malware")
    assert "contain" not in tools_for(actor)
    chosen = llm_messages(actor, {"active_specialty": "malware"})[0]["content"]
    assert chosen.startswith(load_playbook("soc-malware", mode="world"))
    forged = llm_messages(actor, {"active_specialty": "ir"})[0]["content"]
    assert forged.startswith(load_playbook("soc-dfir", mode="world"))
    configured = actor.model_copy(update={"specialties": ("ir",)})
    assert "contain" in tools_for(configured)


@pytest.mark.parametrize(
    "team,role,extra",
    [
        ("red", "access", ("ir",)),
        ("client", "person", ("lead",)),
        ("blue", "dfir", ("unknown",)),
        ("blue", "dfir", ("network", "network")),
    ],
)
def test_invalid_specialties_are_rejected(team, role, extra):
    with pytest.raises(ValidationError):
        Actor(id="test", team=team, role=role, specialties=extra)
