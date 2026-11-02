import hashlib
import io
import json
import tarfile
import uuid

import pytest

from saber.lab.backup import digest, pack, restore
from saber.lab.backup_cli import guest_proof, verify_backup
from saber.lab.deployment import compose, initialize_secrets, render
from saber.lab.ledger import Ledger, now
from saber.lab.models import preset_spec


def test_cold_archive_restores_evidence_outbox_and_uncertain_jobs(tmp_path):
    data = tmp_path / "original"
    store = Ledger(data)
    event = {
        "id": str(uuid.uuid4()),
        "ts": now(),
        "host": "client-test",
        "kind": "file.write",
        "sensor": "test",
        "data": {"synthetic": True},
    }
    store.append(event)
    store.put("job", {"state": "INDETERMINATE", "id": "must-not-be-replayed"})
    (data / "browser.png").write_bytes(b"synthetic-image-fixture")
    store.close()
    archive = tmp_path / "store.tar"
    receipt = pack(data, archive)
    target = tmp_path / "restored"
    restore(archive, target, receipt["sha256"])
    recovered = Ledger(target)
    assert recovered.events(pending=True) == [event]
    assert recovered.get("job")["state"] == "INDETERMINATE"
    assert (target / "browser.png").read_bytes() == b"synthetic-image-fixture"
    recovered.close()
    with pytest.raises(ValueError, match="empty"):
        restore(archive, target, receipt["sha256"])
    archive.write_bytes(archive.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        restore(archive, tmp_path / "reject", receipt["sha256"])
    assert not (tmp_path / "reject").exists()


@pytest.mark.parametrize(
    "member,kind",
    [
        ("../escape", "file"),
        ("/absolute", "file"),
        ("C:/escape", "file"),
        ("link", "symlink"),
        ("link", "hardlink"),
        ("pipe", "fifo"),
    ],
)
def test_archive_rejects_escape_and_special_members_before_writing(tmp_path, member, kind):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as stream:
        item = tarfile.TarInfo(member)
        item.type = {
            "symlink": tarfile.SYMTYPE,
            "hardlink": tarfile.LNKTYPE,
            "fifo": tarfile.FIFOTYPE,
        }.get(kind, tarfile.REGTYPE)
        item.linkname = "../escape" if "link" in kind else ""
        stream.addfile(item, io.BytesIO())
    with pytest.raises(ValueError, match="Unsafe"):
        restore(archive, tmp_path / "target", digest(archive))
    assert not (tmp_path / "target").exists()


def test_complete_backup_manifest_detects_missing_or_changed_volume(tmp_path):
    bundle, folder = tmp_path / "bundle", tmp_path / "backup"
    spec = preset_spec("linux-small")
    render(spec, bundle)
    initialize_secrets(bundle, spec)
    folder.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture").write_text("SYNTHETIC")
    manifest = {
        "schema_version": 1,
        "id": str(uuid.uuid4()),
        "bundle_sha256": digest(bundle / "manifest.json"),
        "lab_sha256": digest(bundle / "lab.json"),
        "volumes": {
            name: pack(source, folder / (name + ".tar")) for name in compose(spec)["volumes"]
        },
        "credentials": pack(bundle / ".secrets", folder / "credentials.tar"),
    }
    (folder / "backup.json").write_text(json.dumps(manifest))
    assert verify_backup(folder, bundle)["id"] == manifest["id"]
    # Even a checksum consistent with a traversal payload must not pass validation.
    with tarfile.open(folder / "client.tar", "w") as stream:
        stream.addfile(tarfile.TarInfo("../out"), io.BytesIO())
    raw = (folder / "client.tar").read_bytes()
    manifest["volumes"]["client"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["volumes"]["client"]["bytes"] = len(raw)
    (folder / "backup.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_backup(folder, bundle)


def test_guest_backup_hash_uses_actual_spec_bytes_and_requires_complete_export(tmp_path):
    spec = preset_spec("windows-ad")
    lab_file = tmp_path / "lab.json"
    lab_file.write_bytes(spec.model_dump_json(indent=2).replace("\n", "\r\n").encode())
    folder = tmp_path / "guests"
    folder.mkdir()
    names = [spec.name + "-" + n.name for n in spec.windows]
    files, configs = {}, {}
    for name in names:
        for relative in (name + "/Virtual Machines/vm.vmcx", name + "/Disks/disk.vhdx"):
            file = folder / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b"SYNTHETIC EXPORT STRUCTURE FIXTURE")
            files[relative] = digest(file)
        configs[name] = name + "/Virtual Machines/vm.vmcx"
    proof = {
        "lab_sha256": digest(lab_file),
        "all_off": True,
        "vms": names,
        "files": files,
        "configs": configs,
    }
    manifest = folder / "windows-manifest.json"
    manifest.write_text(json.dumps(proof), encoding="utf-8-sig")
    assert guest_proof(folder, spec, digest(lab_file)) == proof
    del proof["files"][names[0] + "/Disks/disk.vhdx"]
    manifest.write_text(json.dumps(proof), encoding="utf-8-sig")
    with pytest.raises(ValueError, match="lacks"):
        guest_proof(folder, spec, digest(lab_file))
