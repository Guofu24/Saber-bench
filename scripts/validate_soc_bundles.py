"""Render all three presets and validate Compose without starting an engine or reading keys."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from saber.lab.deployment import initialize_secrets, render, verify_bundle
from saber.lab.models import preset_spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, required=True, help="New output directory, normally under runs/"
    )
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a new output directory")
    args.out.mkdir(parents=True)
    docker = shutil.which("docker")
    report = {
        "schema_version": 1,
        "runtime_verified": False,
        "presets": [],
        "scope": "schema, source manifest and Compose parsing only",
    }
    for name in ("linux-small", "windows-ad", "expanded"):
        spec = preset_spec(name)
        root = args.out / name
        render(spec, root)
        initialize_secrets(root, spec)
        verify_bundle(root)
        # Generated fixture credentials only; never open the operator's provider pool.
        fixture = root / ".secrets/fixture-pool.txt"
        fixture.write_text("fixture-only-not-a-provider-key\n", encoding="ascii")
        env = os.environ | {
            "SABER_GEMINI_POOL": str(fixture.resolve()),
            "SABER_CALL_BUDGET": "1",
            "SABER_MODEL": "fixture-model",
        }
        modes = {}
        for mode in ("scripted", "gemini"):
            if not docker:
                modes[mode] = "NOT_RUN_DOCKER_CLI_MISSING"
                continue
            files = ["-f", str((root / "compose.yaml").resolve())]
            if mode == "gemini":
                files += ["-f", str((root / "compose.gemini.yaml").resolve())]
            result = subprocess.run(
                [docker, "compose", *files, "config", "--quiet"],
                capture_output=True,
                timeout=30,
                env=env,
            )
            modes[mode] = "PASS" if result.returncode == 0 else "FAIL"
        report["presets"].append({"preset": name, "manifest": "PASS", "compose": modes})
    report["passed"] = all(
        row["compose"][mode] == "PASS"
        for row in report["presets"]
        for mode in ("scripted", "gemini")
    )
    (args.out / "validation.receipt.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
