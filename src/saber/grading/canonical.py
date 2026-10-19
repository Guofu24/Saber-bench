"""Canonicalisers for set elements. Each returns a stable string key; see ADR 0001."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

Canonicalizer = Callable[[Any], str]

_WS = re.compile(r"\s+")
_TECH = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_DEFANG = [
    (re.compile(r"\[\.\]|\(\.\)|\{\.\}|\[dot\]", re.I), "."),
    (re.compile(r"hxxp", re.I), "http"),
    (re.compile(r"\[:\]|\[://\]"), "://"),
    (re.compile(r"\[@\]|\(at\)", re.I), "@"),
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return _WS.sub(" ", str(value)).strip()


def canon_text(value: Any) -> str:
    return _text(value).lower()


def canon_exact(value: Any) -> str:
    return _text(value)


def canon_int(value: Any) -> str:
    text = _text(value)
    try:
        return str(int(float(text)))
    except ValueError:
        return text.lower()


def canon_ip(value: Any) -> str:
    text = _text(value)
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text.lower()


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def canon_host(value: Any) -> str:
    text = _text(value).lower().rstrip(".")
    if _is_ip(text):
        return canon_ip(text)
    if "\\" in text:  # DOMAIN\host
        text = text.split("\\", 1)[1]
    return text.split(".", 1)[0] if text and not text[0].isdigit() else text


def canon_sha256(value: Any) -> str:
    text = _text(value).lower()
    return text if re.fullmatch(r"[0-9a-f]{64}", text) else text


def canon_hash(value: Any) -> str:
    return _text(value).lower()


def canon_proc(value: Any) -> str:
    text = _text(value).strip("\"'").replace("\\", "/")
    base = text.rsplit("/", 1)[-1].lower()
    return base


def canon_account(value: Any) -> str:
    text = _text(value).lower()
    if "\\" in text:
        text = text.split("\\", 1)[1]
    if "@" in text and not text.startswith("@"):
        text = text.split("@", 1)[0]
    return text


def canon_email(value: Any) -> str:
    return _text(value).lower()


def canon_path(value: Any) -> str:
    text = _text(value).strip("\"'").replace("\\", "/")
    if len(text) > 1 and text.rstrip("/") != "/":
        text = text.rstrip("/")
    if re.match(r"^[a-zA-Z]:/", text):
        text = text.lower()
    return text


def canon_technique(value: Any) -> str:
    text = _text(value).upper().replace(" ", "")
    match = re.search(r"T\d{4}(?:\.\d{3})?", text)
    return match.group(0) if match else text


def canon_tactic(value: Any) -> str:
    text = _text(value).lower().replace("_", "-").replace(" ", "-")
    return re.sub(r"^ta\d{4}-", "", text)


def canon_ioc(value: Any) -> str:
    text = _text(value)
    for pattern, repl in _DEFANG:
        text = pattern.sub(repl, text)
    text = text.lower().strip()
    if text.startswith(("http://", "https://")):
        text = text.rstrip("/")
    return text.rstrip(".")


def canon_port(value: Any) -> str:
    return canon_int(value)


def _parts(value: Any, n: int) -> list[Any]:
    if isinstance(value, Mapping):
        return (
            list(value.values())[:n]
            if len(value) >= n
            else list(value.values()) + [None] * (n - len(value))
        )
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        items = list(value)
        return items[:n] + [None] * (n - len(items))
    text = _text(value)
    sep = (
        ","
        if "," in text
        else ("|" if "|" in text else (":" if n == 2 and text.count(":") == 1 else " "))
    )
    items = [p.strip() for p in text.split(sep)]
    return items[:n] + [None] * (n - len(items))


def make_tuple_canon(
    *part_canons: Canonicalizer, keys: Sequence[str] | None = None
) -> Canonicalizer:
    """Canonicalise composite elements given as dict (by keys), list/tuple, or delimited text."""

    def canon(value: Any) -> str:
        if keys and isinstance(value, Mapping):
            parts = [value.get(k) for k in keys]
        else:
            parts = _parts(value, len(part_canons))
        return "|".join(fn(p) for fn, p in zip(part_canons, parts, strict=True))

    return canon


_SIMPLE: dict[str, Canonicalizer] = {
    "host": canon_host,
    "ip": canon_ip,
    "sha256": canon_sha256,
    "hash": canon_hash,
    "proc": canon_proc,
    "process": canon_proc,
    "acct": canon_account,
    "account": canon_account,
    "contact": canon_email,
    "email": canon_email,
    "line": canon_int,
    "pid": canon_int,
    "field": canon_text,
    "rule": canon_text,
    "case_id": canon_text,
    "technique": canon_technique,
    "ATT&CK": canon_technique,
    "tactic": canon_tactic,
    "ioc": canon_ioc,
    "path": canon_path,
    "action": canon_text,
    "step": canon_text,
    "section": canon_text,
    "config": canon_text,
    "source": canon_text,
    "normalized": canon_text,
    "recall": canon_text,
    "text": canon_text,
    "port": canon_port,
}

_COMPOSITE: dict[str, Canonicalizer] = {
    "(ip,port)": make_tuple_canon(canon_ip, canon_port, keys=("ip", "port")),
    "(ip,port,proc)": make_tuple_canon(
        canon_ip, canon_port, canon_proc, keys=("ip", "port", "process")
    ),
    "(src,dst)": make_tuple_canon(canon_host, canon_host, keys=("src", "dst")),
    "(src,dst,acct)": make_tuple_canon(
        canon_host, canon_host, canon_account, keys=("src", "dst", "account")
    ),
    "(src,dst,acct,logon)": make_tuple_canon(
        canon_host,
        canon_host,
        canon_account,
        canon_text,
        keys=("src", "dst", "account", "logon_type"),
    ),
    "(act,obj,layer)": make_tuple_canon(
        canon_text, canon_text, canon_text, keys=("action", "object", "layer")
    ),
    "(obj,layer)": make_tuple_canon(canon_text, canon_text, keys=("object", "layer")),
    "(loại,vị trí)": make_tuple_canon(canon_text, canon_path, keys=("kind", "location")),
    "(pid,module)": make_tuple_canon(canon_int, canon_proc, keys=("pid", "module")),
    "(hash,host)": make_tuple_canon(canon_hash, canon_host, keys=("hash", "host")),
    "source+rule": make_tuple_canon(canon_text, canon_text, keys=("source", "rule")),
    "tuple": make_tuple_canon(canon_text, canon_text, keys=("a", "b")),
}


def canonicalizer_for(subtype: str | None) -> Canonicalizer:
    if subtype is None:
        return canon_text
    key = subtype.strip()
    if key in _COMPOSITE:
        return _COMPOSITE[key]
    if key in _SIMPLE:
        return _SIMPLE[key]
    return canon_text


def canonical_set(values: Any, canon: Canonicalizer) -> set[str]:
    """Dedupe + canonicalise; `None`/missing treated as empty; drops empty keys."""
    if values is None:
        return set()
    if isinstance(values, str | bytes | Mapping):
        values = [values]
    out: set[str] = set()
    for item in values:
        key = canon(item)
        if key and key != "|" and not all(ch == "|" for ch in key):
            out.add(key)
    return out
