"""Capabilities describe delivered behavior, not installed vendor products."""

from typing import Any

from saber.environments.models import ProfileName

PROFILES: dict[ProfileName, dict[str, Any]] = {
    "local": {
        "location": "Current Python host",
        "isolation": "Application roles and HTTP capabilities; no OS sandbox",
        "prerequisites": ["Python >= 3.12 and project dependencies"],
        "use_when": "Development, low-resource demos and offline benchmark work",
    },
    "sandbox": {
        "location": "One hardened Linux container containing the application world",
        "isolation": "Container boundary around the world; native workers share its kernel/user",
        "prerequisites": ["Docker Linux engine", "Docker Compose", "Image build access"],
        "use_when": "A reproducible disposable application lab without managing a VM",
    },
    "vm": {
        "location": "Inside an operator-created Windows or Linux VM",
        "isolation": "Guest OS boundary managed by the operator's hypervisor",
        "prerequisites": ["An existing VM", "Python >= 3.12 and uv inside the VM"],
        "use_when": "Keep the runtime in a dedicated guest; operator owns VM sizing/snapshots",
    },
    "remote": {
        "location": "On an operator-managed lab server after transferring the bundle",
        "isolation": "Depends on the supplied server/VM; no automatic remote provisioning",
        "prerequisites": ["An existing lab server", "Python >= 3.12 and uv on that server"],
        "use_when": "Offload CPU/RAM/storage from the workstation; run commands on the server",
    },
}


def describe(profile: ProfileName) -> dict[str, Any]:
    return {
        "profile": profile,
        **PROFILES[profile],
        "runtime": "Continuous application world (scripted or opt-in Gemini)",
        "labels": ["LOCAL_APPLICATION_LAB", "DEV_SIMULATION_ONLY"],
        "included": ["client/red/blue actors", "HTTP application effects", "durable logs/cases"],
        "not_implemented": [
            "Per-actor desktops or OS agents",
            "Browser automation and arbitrary OS commands",
            "Hypervisor provisioning or snapshot control",
            "Vendor SIEM/SOAR data and response adapters",
        ],
    }
