"""Streaming UTF-8 parsers. Normalized fields are derivatives, never original evidence."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO

RECORD_LIMIT = 131072
TEXT_LIMIT = 16384
FIELDS = {
    "host": ("Computer", "ComputerName", "Hostname", "Host", "DeviceName"),
    "image": ("Image", "ProcessImage", "ProcessName", "FileName"),
    "parent_image": ("ParentImage", "ParentProcessName"),
    "process_guid": ("ProcessGuid", "ProcessUniqueId"),
    "parent_guid": ("ParentProcessGuid",),
    "pid": ("ProcessId", "PID"),
    "parent_pid": ("ParentProcessId", "PPID"),
    "event_id": ("EventID", "EventCode"),
    "command_line": ("CommandLine", "ProcessCommandLine"),
    "ip": ("SourceIp", "ClientIP", "RemoteIP", "c-ip"),
    "destination_ip": ("DestinationIp", "DestinationAddress"),
    "uri": ("Uri", "Url", "cs-uri-stem"),
    "status": ("StatusCode", "sc-status", "Status"),
    "provider": ("ProviderName", "Provider", "SourceName"),
    "timestamp_raw": ("UtcTime", "Timestamp", "TimeCreated", "DateTime", "@timestamp"),
}
APACHE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "([^"\r\n]*)" (\d{3}) (?:\d+|-)')
ISO = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?")


def utc(value: str, assumed_offset: str | None = None) -> str | None:
    """Do not invent a date/year/zone. Keep the original timestamp separately."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%d/%b/%Y:%H:%M:%S %z")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        if assumed_offset is None:
            return None
        if not re.fullmatch(r"[+-](?:0\d|1[0-4]):[0-5]\d", assumed_offset):
            raise ValueError("Use a fixed offset such as +07:00")
        minutes = int(assumed_offset[1:3]) * 60 + int(assumed_offset[4:])
        if minutes > 840:
            raise ValueError("Timezone offset exceeds 14 hours")
        parsed = parsed.replace(
            tzinfo=timezone(timedelta(minutes=minutes * (-1 if assumed_offset[0] == "-" else 1)))
        )
    return parsed.astimezone(UTC).isoformat(timespec="microseconds")


def normalize(row: dict[str, str], assumed_offset: str | None) -> dict[str, Any]:
    lookup = {k.strip().casefold(): v for k, v in row.items()}
    out: dict[str, Any] = {
        field: next((lookup[a.casefold()] for a in aliases if lookup.get(a.casefold())), "")
        for field, aliases in FIELDS.items()
    }
    # UtcTime explicitly declares UTC; a plain Timestamp does not.
    out["ts"] = utc(out["timestamp_raw"], "+00:00" if "utctime" in lookup else assumed_offset)
    return out


class Lines:
    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream

    def __iter__(self) -> Lines:
        return self

    def __next__(self) -> str:
        raw = self.stream.readline(RECORD_LIMIT + 1)
        if not raw:
            raise StopIteration
        if len(raw) > RECORD_LIMIT:
            raise ValueError("physical_line_limit")
        return raw.decode("utf-8-sig", errors="strict")


def records(path: Path, fmt: str, offset: str | None) -> Iterator[dict[str, Any]]:
    with path.open("rb") as stream:
        lines = Lines(stream)
        reader = csv.reader(lines, strict=True) if fmt == "csv" else None
        header: list[str] = []
        if reader:
            header = next(reader, [])
            if not header or len(set(h.strip().casefold() for h in header)) != len(header):
                raise ValueError("missing_or_duplicate_csv_columns")
        while True:
            start = stream.tell()
            try:
                if reader:
                    cells = next(reader)
                    row = dict(zip(header, cells, strict=True))
                    data = normalize(row, offset)
                else:
                    line = next(lines).rstrip("\r\n")
                    if fmt == "iis" and line.startswith("#Fields:"):
                        header = line[8:].split()
                        continue
                    if fmt == "iis" and (line.startswith("#") or not line):
                        continue
                    if fmt == "iis":
                        if not header:
                            raise ValueError("iis_requires_fields_header")
                        row = dict(zip(header, line.split(), strict=True))
                        row["UtcTime"] = row.get("date", "") + "T" + row.get("time", "")
                        data = normalize(row, "+00:00")
                    elif fmt == "apache":
                        match = APACHE.match(line)
                        if match:
                            ip, ts, request, status = match.groups()
                            parts = request.split(" ")
                            data = normalize(
                                {
                                    "ClientIP": ip,
                                    "Timestamp": ts,
                                    "Uri": parts[1] if len(parts) > 1 else "",
                                    "Status": status,
                                },
                                offset,
                            )
                        else:
                            data = {"parse_error": "unrecognized_apache_record", "ts": None}
                    else:
                        match = ISO.search(line)
                        data = normalize({"Timestamp": match[0] if match else ""}, offset)
                end = stream.tell()
                if end - start > RECORD_LIMIT:
                    raise ValueError("logical_record_limit")
                yield {"offset": start, "length": end - start, "fields": data}
            except StopIteration:
                break
