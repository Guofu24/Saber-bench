"""Fixed offline analyzer invocations over immutable operator-provided lab samples."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from saber.lab.events import redact

Engine = Literal["builtin", "ghidra", "ida", "volatility", "yara", "tshark", "suricata"]
ENGINES = ("builtin", "ghidra", "ida", "volatility", "yara", "tshark", "suricata")
PLUGIN = {
    "windows-processes": "windows.pslist.PsList",
    "windows-network": "windows.netscan.NetScan",
    "linux-processes": "linux.pslist.PsList",
}


class AnalysisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    memory_gb: int = Field(default=2, ge=1, le=64)
    timeout_seconds: int = Field(default=180, ge=5, le=1800)
    max_sample_mb: int = Field(default=512, ge=1, le=16384)
    ghidra: str = "/opt/tools/ghidra/support/analyzeHeadless"
    ida: str = "/opt/tools/ida/idat"
    symbols: str = "/opt/tools/symbols"


class AnalysisJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    sample_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    engine: Engine
    profile: Literal["default", "windows-processes", "windows-network", "linux-processes"] = (
        "default"
    )


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def availability(settings: AnalysisSettings) -> dict[str, dict[str, Any]]:
    values = {
        "builtin": True,
        "ghidra": Path(settings.ghidra).is_file(),
        "ida": Path(settings.ida).is_file(),
        "volatility": importlib.util.find_spec("volatility3") is not None,
        "yara": shutil.which("yara") is not None or importlib.util.find_spec("yara") is not None,
        **{n: shutil.which(n) is not None for n in ("tshark", "suricata")},
    }
    return {
        n: {
            "available": ok,
            "status": "available" if ok else "dependency_missing",
            "runtime_verified": False,
        }
        for n, ok in values.items()
    }


def argv_for(
    job: AnalysisJob, sample: Path, directory: Path, assets: Path, settings: AnalysisSettings
) -> list[str]:
    source = str(sample)
    if job.engine == "ghidra":
        return [
            settings.ghidra,
            str(directory),
            "project",
            "-import",
            source,
            "-analysisTimeoutPerFile",
            str(max(1, settings.timeout_seconds - 10)),
            "-max-cpu",
            "1",
            "-scriptPath",
            str(assets),
            "-postScript",
            "ExportSummary.java",
            str(directory / "summary.json"),
            "-deleteProject",
        ]
    if job.engine == "ida":
        return [
            settings.ida,
            "-A",
            "-S" + str(assets / "ida_summary.py"),
            "-o" + str(directory / "sample.i64"),
            source,
        ]
    if job.engine == "volatility":
        if job.profile not in PLUGIN:
            raise ValueError("Select an allowlisted memory profile")
        return [
            sys.executable,
            "-m",
            "saber.lab.volatility_tool",
            "-q",
            "--offline",
            "--cache-path",
            str(directory / "cache"),
            "-s",
            settings.symbols,
            "-r",
            "json",
            "-f",
            source,
            PLUGIN[job.profile],
        ]
    if job.engine == "yara" and not shutil.which("yara"):
        return [sys.executable, "-m", "saber.lab.yara_tool", str(assets / "saber.yar"), source]
    exe = shutil.which(job.engine)
    if not exe:
        raise FileNotFoundError("Analyzer dependency missing")
    if job.engine == "yara":
        return [exe, str(assets / "saber.yar"), source]
    if job.engine == "tshark":
        return [
            exe,
            "-n",
            "-r",
            source,
            "-c",
            "1000",
            "-T",
            "json",
            "-e",
            "frame.number",
            "-e",
            "ip.src",
            "-e",
            "ip.dst",
            "-e",
            "tcp.dstport",
            "-e",
            "dns.qry.name",
        ]
    if job.engine == "suricata":
        return [
            exe,
            "--runmode",
            "single",
            "-r",
            source,
            "-S",
            str(assets / "saber.rules"),
            "-c",
            str(assets / "suricata.yaml"),
            "-l",
            str(directory),
        ]
    raise ValueError("Unsupported analyzer")


def builtin(sample: Path, kind: str) -> dict[str, Any]:
    with sample.open("rb") as stream:
        data = stream.read(2_000_000)
    counts = Counter(data)
    entropy = -sum(n / len(data) * math.log2(n / len(data)) for n in counts.values()) if data else 0
    result: dict[str, Any] = {
        "kind": kind,
        "bytes": sample.stat().st_size,
        "inspected_bytes": len(data),
        "entropy": round(entropy, 4),
        "format": "unknown",
        "scope": "static metadata, not a malware verdict",
    }
    if data.startswith(b"MZ") and len(data) >= 64:
        offset = struct.unpack_from("<I", data, 60)[0]
        if offset + 24 <= len(data) and data[offset : offset + 4] == b"PE\0\0":
            machine, sections = struct.unpack_from("<HH", data, offset + 4)
            result.update(format="PE", machine=machine, sections=sections)
    elif data.startswith(b"\x7fELF") and len(data) >= 20:
        result.update(format="ELF", bits=32 if data[4] == 1 else 64, endianness=data[5])
    elif data[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x0a\x0d\x0d\x0a"):
        result["format"] = "PCAP"
    if kind == "binary":
        result["strings"] = [s.decode("ascii")[:256] for s in re.findall(rb"[ -~]{8,}", data)[:100]]
    return result


def execute(
    job: AnalysisJob,
    sample: Path,
    kind: str,
    directory: Path,
    assets: Path,
    settings: AnalysisSettings,
) -> dict[str, Any]:
    if sample.is_symlink() or not sample.is_file() or file_hash(sample) != job.sample_id:
        raise ValueError("Sample integrity failed")
    if not availability(settings)[job.engine]["available"]:
        return {"state": "UNAVAILABLE", "error": "Analyzer dependency missing"}
    if job.engine in ("ghidra", "ida", "yara") and kind != "binary":
        raise ValueError("Binary sample required")
    if job.engine == "volatility" and kind != "memory":
        raise ValueError("Memory image required")
    if job.engine in ("tshark", "suricata") and kind != "pcap":
        raise ValueError("PCAP sample required")
    directory.mkdir(parents=True, exist_ok=False)
    start, pid, exit_code = time.monotonic(), os.getpid(), 0
    if job.engine == "builtin":
        result = builtin(sample, kind)
    else:
        argv = argv_for(job, sample, directory, assets, settings)
        env = {
            k: os.environ[k]
            for k in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "JAVA_HOME")
            if k in os.environ
        }
        env.update(PYTHONNOUSERSITE="1", TVHEADLESS="1")
        home = directory / "home"
        home.mkdir()
        (home / "ida").mkdir()
        env.update(
            HOME=str(home),
            USERPROFILE=str(home),
            IDAUSR=str(home / "ida"),
            XDG_CACHE_HOME=str(home / "cache"),
        )
        # Ghidra's launcher also uses Java's home property; UID 10001 has no passwd entry.
        if job.engine == "ghidra":
            env["JAVA_TOOL_OPTIONS"] = '-Duser.home="' + str(home) + '"'
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        log = directory / "stdout.log"
        error_log = directory / "stderr.log"
        with log.open("xb") as output, error_log.open("xb") as errors:
            process = subprocess.Popen(
                argv,
                cwd=directory,
                env=env,
                stdout=output,
                stderr=errors,
                stdin=subprocess.DEVNULL,
                start_new_session=os.name == "posix",
            )
            pid = process.pid
            failure = None
            try:
                while process.poll() is None:
                    size = sum(
                        p.stat().st_size
                        for p in directory.rglob("*")
                        if p.is_file() and not p.is_symlink()
                    )
                    if (
                        time.monotonic() - start > settings.timeout_seconds
                        or size > 128_000_000
                        or log.stat().st_size + error_log.stat().st_size > 2_000_000
                    ):
                        failure = "Timeout or output budget reached"
                        break
                    time.sleep(0.1)
            finally:
                if process.poll() is None:
                    if sys.platform != "win32":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                exit_code = process.wait()
        if failure or exit_code != 0:
            return {
                "state": "FAILED",
                "pid": pid,
                "exit_code": exit_code,
                "error": failure or "Analyzer returned a nonzero exit code; no verdict inferred",
            }
        report = (
            directory / "summary.json"
            if job.engine in ("ghidra", "ida")
            else directory / "eve.json"
            if job.engine == "suricata"
            else log
        )
        if not report.is_file() or report.is_symlink() or report.stat().st_size > 2_000_000:
            raise ValueError("Analyzer report missing or oversized")
        raw = report.read_text(encoding="utf-8", errors="replace")
        if job.engine in ("ghidra", "ida", "volatility", "tshark"):
            parsed = json.loads(raw)
            if job.engine in ("ghidra", "ida"):
                if (
                    not isinstance(parsed, dict)
                    or parsed.get("analysis_completed") is not True
                    or not isinstance(parsed.get("functions"), list)
                ):
                    raise ValueError("Native analysis incomplete or report schema invalid")
            elif not isinstance(parsed, list):
                raise ValueError("Expected native JSON record list")
            result = {"report": parsed}
        elif job.engine == "suricata":
            result = {"events": [json.loads(line) for line in raw.splitlines()[:1000]]}
        else:
            result = {
                "matches": [line.split(" ", 1)[0] for line in raw.splitlines() if line.strip()],
                "rule_scope": "bundled synthetic marker rule; no clean/malicious verdict",
            }
    if file_hash(sample) != job.sample_id:
        raise ValueError("Analyzer changed its input")
    value = {
        "state": "SUCCEEDED",
        "engine": job.engine,
        "profile": job.profile,
        "sample_id": job.sample_id,
        "pid": pid,
        "exit_code": exit_code,
        "duration_ms": round((time.monotonic() - start) * 1000),
        "result": redact(result),
    }
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    if len(encoded) > 1_500_000:
        raise ValueError("Normalized analysis exceeds budget")
    (directory / "analysis.json").write_bytes(encoded)
    return value | {"report_sha256": hashlib.sha256(encoded).hexdigest()}
