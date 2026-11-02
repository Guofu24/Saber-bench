"""Streaming, integrity-checked cold archives. Never overwrite a populated destination."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_archive(path: Path) -> dict[str, int]:
    seen: set[str] = set()
    size = 0
    with tarfile.open(path, "r:") as archive:
        for item in archive:
            name = PurePosixPath(item.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in item.name
                or ":" in item.name
                or item.name in seen
                or not (item.isfile() or item.isdir())
                or item.size < 0
            ):
                raise ValueError("Unsafe archive member")
            seen.add(item.name)
            size += item.size
            if len(seen) > 2_000_000:
                raise ValueError("Archive member budget exceeded")
    return {"members": len(seen), "unpacked_bytes": size}


def pack(source: Path, archive: Path) -> dict[str, Any]:
    if source.is_symlink() or not source.is_dir() or archive.exists():
        raise ValueError("Expected real source and new archive")
    source = source.resolve()
    if archive.resolve().is_relative_to(source):
        raise ValueError("Archive cannot be inside source")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "x:", dereference=True) as output:
        for path in [source, *sorted(source.rglob("*"))]:
            mode = path.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError("Source contains links or special files")
            output.add(
                path,
                arcname="." if path == source else path.relative_to(source).as_posix(),
                recursive=False,
            )
    archive.chmod(0o600)
    return {"sha256": digest(archive), "bytes": archive.stat().st_size, **inspect_archive(archive)}


def restore(archive: Path, target: Path, expected_sha256: str) -> None:
    if digest(archive) != expected_sha256:
        raise ValueError("Archive checksum mismatch")
    inspected = inspect_archive(archive)
    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise ValueError("Restore requires an empty real directory")
    target.mkdir(parents=True, exist_ok=True)
    target = target.resolve()
    if shutil.disk_usage(target).free < inspected["unpacked_bytes"] + 16 * 1024 * 1024:
        raise OSError("Insufficient restore space")
    directories = []
    with tarfile.open(archive, "r:") as source:
        for item in source:
            path = target / item.name
            if not path.resolve().is_relative_to(target):
                raise ValueError("Archive escaped destination")
            if item.isdir():
                path.mkdir(parents=True, exist_ok=True)
                directories.append((path, item))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                stream = source.extractfile(item)
                if stream is None:
                    raise ValueError("Unreadable archive member")
                with stream, path.open("xb") as dest:
                    shutil.copyfileobj(stream, dest, 1024 * 1024)
                    dest.flush()
                    os.fsync(dest.fileno())
                metadata(path, item)
    for path, item in reversed(directories):
        metadata(path, item)


def metadata(path: Path, item: tarfile.TarInfo) -> None:
    native: Any = os
    if os.name == "posix" and native.geteuid() == 0:
        native.chown(path, item.uid, item.gid)
    path.chmod(item.mode & 0o777)
    os.utime(path, (item.mtime, item.mtime))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["pack", "restore"])
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if args.mode == "pack":
        print(json.dumps(pack(args.directory, args.archive)))
    else:
        restore(args.archive, args.directory, args.sha256)
        print(json.dumps({"restored": True}))


if __name__ == "__main__":
    main()
