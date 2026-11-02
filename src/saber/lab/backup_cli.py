"""Coordinated Docker cold backup and restore to new, explicitly owned volumes."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import click

from saber.lab.backup import digest, inspect_archive, pack, restore
from saber.lab.deployment import compose, verify_bundle
from saber.lab.ledger import now


def docker(args: list[str], timeout: int = 60) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError("Docker backup operation failed; private diagnostics suppressed")
    return result.stdout.decode("utf-8").strip()


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True)
    if os.name == "nt":
        identity = (
            subprocess.run(["whoami"], capture_output=True, check=True).stdout.decode().strip()
        )
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", identity + ":(OI)(CI)F"],
            capture_output=True,
            check=True,
        )


def guest_proof(folder: Path, spec: Any, lab_sha256: str) -> dict[str, Any]:
    proof = json.loads((folder / "windows-manifest.json").read_text(encoding="utf-8-sig"))
    if proof["lab_sha256"] != lab_sha256 or proof.get("all_off") is not True:
        raise ValueError("Guest backup belongs to another lab or was not stopped")
    if set(proof["vms"]) != {spec.name + "-" + n.name for n in spec.windows}:
        raise ValueError("Incomplete guest backup roster")
    if folder.is_symlink() or set(proof.get("configs", {})) != set(proof["vms"]):
        raise ValueError("Incomplete guest configurations")
    for vm in proof["vms"]:
        if proof["configs"][vm] not in proof["files"] or not any(
            name.startswith(vm + "/") and name.lower().endswith((".vhdx", ".avhdx"))
            for name in proof["files"]
        ):
            raise ValueError("Guest export lacks configuration or disk")
    for name, checksum in proof["files"].items():
        path = folder / name
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(folder.resolve())
            or digest(path) != checksum
        ):
            raise ValueError("Guest export integrity mismatch")
    return dict(proof)


def verify_backup(folder: Path, bundle: Path, windows_backup: Path | None = None) -> dict[str, Any]:
    spec = verify_bundle(bundle)
    manifest = json.loads((folder / "backup.json").read_text())
    if (
        manifest.get("schema_version") != 1
        or manifest["bundle_sha256"] != digest(bundle / "manifest.json")
        or manifest["lab_sha256"] != digest(bundle / "lab.json")
    ):
        raise ValueError("Backup needs the exact original verified bundle")
    if set(manifest["volumes"]) != set(compose(spec)["volumes"]):
        raise ValueError("Incomplete volume backup")
    for key, record in {**manifest["volumes"], "credentials": manifest["credentials"]}.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", key):
            raise ValueError("Invalid volume name")
        path = folder / (key + ".tar")
        if (
            path.is_symlink()
            or path.stat().st_size != record["bytes"]
            or digest(path) != record["sha256"]
        ):
            raise ValueError("Backup checksum mismatch")
        if inspect_archive(path) != {k: record[k] for k in ("members", "unpacked_bytes")}:
            raise ValueError("Backup archive structure mismatch")
    if spec.windows and (
        windows_backup is None
        or guest_proof(windows_backup, spec, digest(bundle / "lab.json")) != manifest.get("windows")
    ):
        raise ValueError("Matching complete Windows export required")
    return dict(manifest)


@click.group(
    "backup", help="Cold backup, verify and restore; archives contain private lab credentials."
)
def backup_cli() -> None:
    pass


@backup_cli.command("create")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--windows-backup", type=click.Path(path_type=Path, exists=True))
@click.option("--on-target", is_flag=True)
def create(bundle: Path, out: Path, windows_backup: Path | None, on_target: bool) -> None:
    from saber.lab.cli import compose_command

    try:
        if not on_target or out.exists():
            raise ValueError("Use --on-target and a new private backup directory")
        spec = verify_bundle(bundle)
        guests = (
            guest_proof(windows_backup, spec, digest(bundle / "lab.json"))
            if windows_backup
            else None
        )
        if spec.windows and guests is None:
            raise ValueError("Export and stop all Windows guests first")
        if not (bundle / ".secrets").is_dir():
            raise ValueError("Existing deployment credentials required")
        permitted = {
            n + ".json"
            for n in (
                "app",
                "controller",
                "collector",
                "client",
                "red",
                "blue",
                "network",
                "linux-audit",
                "relay",
                "analysis",
                "soar",
            )
        }
        if {p.name for p in (bundle / ".secrets").iterdir()} != permitted:
            raise ValueError(
                "Backup requires only generated service credentials in .secrets; keep provider keys outside"
            )
        compose_command(bundle, ["stop", "-t", "60", "controller"])
        compose_command(bundle, ["stop", "-t", "60"])
        definitions = compose(spec)["volumes"]
        for name in definitions:
            volume = spec.name + "_" + name
            info = json.loads(docker(["volume", "inspect", volume]))[0]
            if info.get("Labels", {}).get("com.docker.compose.project") != spec.name:
                raise ValueError("Volume ownership mismatch")
            if docker(["ps", "-q", "--filter", "volume=" + volume]):
                raise ValueError("A backup volume still has running consumers")
        private_directory(out)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "id": str(uuid.uuid4()),
            "created_at": now(),
            "bundle_sha256": digest(bundle / "manifest.json"),
            "lab_sha256": digest(bundle / "lab.json"),
            "volumes": {},
            "windows": guests,
        }
        # Uses the installed, manifest-bound collector image, no network or Docker socket.
        image = compose(spec)["services"]["collector"]["image"]
        for name in definitions:
            manifest["volumes"][name] = json.loads(
                docker(
                    [
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--read-only",
                        "--user",
                        "0:0",
                        "--mount",
                        f"type=volume,src={spec.name}_{name},dst=/input,readonly",
                        "--mount",
                        f"type=bind,src={out.resolve()},dst=/backup",
                        image,
                        "python",
                        "-m",
                        "saber.lab.backup",
                        "pack",
                        "--directory",
                        "/input",
                        "--archive",
                        f"/backup/{name}.tar",
                    ],
                    timeout=86400,
                )
            )
        manifest["credentials"] = pack(bundle / ".secrets", out / "credentials.tar")
        (out / "backup.json").write_text(json.dumps(manifest, indent=2))
        # Deliberately exclude provider file and active.receipt.json; opt in again after restore.
        click.echo(
            json.dumps(
                {
                    "backup": str(out),
                    "volumes": len(definitions),
                    "services": "left stopped",
                    "provider_keys": "excluded",
                }
            )
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise click.ClickException(
            "Backup failed; services remain stopped and partial files are preserved. Check target, ownership, guest export, storage and private directory permissions."
        ) from None


@backup_cli.command("verify")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--backup", "folder", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--windows-backup", type=click.Path(path_type=Path, exists=True))
def verify(bundle: Path, folder: Path, windows_backup: Path | None) -> None:
    try:
        manifest = verify_backup(folder, bundle, windows_backup)
        click.echo(
            json.dumps(
                {"verified": True, "id": manifest["id"], "volumes": len(manifest["volumes"])}
            )
        )
    except (OSError, ValueError, KeyError):
        raise click.ClickException("Backup integrity verification failed") from None


@backup_cli.command("restore")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--backup", "folder", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--windows-backup", type=click.Path(path_type=Path, exists=True))
@click.option("--on-target", is_flag=True)
def restore_lab(bundle: Path, folder: Path, windows_backup: Path | None, on_target: bool) -> None:
    from saber.lab.cli import compose_command

    try:
        if not on_target or (bundle / ".secrets").exists():
            raise ValueError("Restore requires --on-target and a fresh copy of original bundle")
        manifest = verify_backup(folder, bundle, windows_backup)
        spec = verify_bundle(bundle)
        existing = set(docker(["volume", "ls", "--format", "{{.Name}}"]).splitlines())
        if any(spec.name + "_" + name in existing for name in manifest["volumes"]):
            raise ValueError("Restore never overwrites existing volumes")
        needed = sum(v["unpacked_bytes"] for v in manifest["volumes"].values())
        # Docker performs its own storage checks; host check covers private configuration restore.
        if (
            shutil.disk_usage(bundle).free
            < manifest["credentials"]["unpacked_bytes"] + 16 * 1024 * 1024
        ):
            raise OSError("Insufficient local storage")
        private_directory(bundle / ".secrets")
        restore(folder / "credentials.tar", bundle / ".secrets", manifest["credentials"]["sha256"])
        compose_command(bundle, ["build", "collector"], {"llm": False})
        image = compose(spec)["services"]["collector"]["image"]
        for name, record in manifest["volumes"].items():
            volume = spec.name + "_" + name
            docker(
                [
                    "volume",
                    "create",
                    "--label",
                    "com.docker.compose.project=" + spec.name,
                    "--label",
                    "com.docker.compose.volume=" + name,
                    "--label",
                    "io.saber.restore=" + manifest["id"],
                    volume,
                ]
            )
            docker(
                [
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--user",
                    "0:0",
                    "--mount",
                    f"type=volume,src={volume},dst=/output",
                    "--mount",
                    f"type=bind,src={folder.resolve()},dst=/backup,readonly",
                    image,
                    "python",
                    "-m",
                    "saber.lab.backup",
                    "restore",
                    "--directory",
                    "/output",
                    "--archive",
                    f"/backup/{name}.tar",
                    "--sha256",
                    record["sha256"],
                ],
                timeout=86400,
            )
        receipt = {
            "restored": True,
            "backup_id": manifest["id"],
            "bytes": needed,
            "runtime_verified": False,
            "services": "not started",
            "provider": "off; explicit opt-in required",
        }
        (bundle / "restore.receipt.json").write_text(json.dumps(receipt, indent=2))
        click.echo(json.dumps(receipt))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise click.ClickException(
            "Restore failed; no existing volume was overwritten. Partial restore is preserved for inspection; use a fresh target after resolving the cause."
        ) from None
