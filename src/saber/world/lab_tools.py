"""Real computations on application evidence; no fabricated native tool output."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from saber.world.operations import Arguments, CaseRef, evidence

if TYPE_CHECKING:
    from saber.world.environment import World
    from saber.world.models import Action, Actor

HELP = {
    "capture_artifact": "Capture immutable application evidence with SHA-256 and custody. args: case_id, kind (events/document/job/identity/service), target optional. Target must occur in case evidence. Not an OS image.",
    "read_artifact": "Read a captured artifact in bounded text pages. args: artifact_id, offset=0, limit=4000 (max 8000).",
    "analyze_artifact": "Analyze stored application JSON bytes: hash, size, observables. args: artifact_id, engine=builtin. Native Ghidra/IDA/Volatility/tshark/YARA/Suricata are blocked until an adapter is configured.",
    "telemetry_health": "Inspect retained event range, counts/errors by source action, retention gaps and adapter availability; no arbitrary host discovery. args: {}.",
    "verify_recovery": "Check current service, mitigation and client activity after case response. args: case_id. Separates available, user-work-observed and integrity-not-measured.",
    "test_rule": "Test application-v1 conditions against cited positive/negative events. args: rule_id, conditions (field/op/value), positive_ids, negative_ids. Fields: tool/status/target/principal/detail.owner; ops eq/ne/gte/lte/ne_field. Labels are caller supplied.",
    "publish_rule": "Publish a tested rule with no errors on its submitted corpus. args: test_id, expected_version (0 if new). Does not publish to external SIEM.",
    "rollback_rule": "Restore a previously published application rule as a new version. args: rule_id, version, expected_version.",
}
ARTIFACT_TOOLS = frozenset({"capture_artifact", "read_artifact", "analyze_artifact"})
RULE_TOOLS = frozenset({"test_rule", "publish_rule", "rollback_rule"})
FIELDS = {"tool", "status", "target", "principal", "detail.owner"}
NATIVE_ENGINES = ("ghidra", "ida", "volatility", "tshark", "yara", "suricata")


class Capture(CaseRef):
    kind: Literal["events", "document", "job", "identity", "service"]
    target: str = Field(default="", max_length=100)


class ArtifactRef(Arguments):
    artifact_id: str = Field(pattern=r"^artifact-[a-f0-9]{24}$")


class ArtifactPage(ArtifactRef):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=4000, ge=1, le=8000)


class Analyze(ArtifactRef):
    engine: Literal["builtin", "ghidra", "ida", "volatility", "tshark", "yara", "suricata"] = (
        "builtin"
    )


class Condition(Arguments):
    field: Literal["tool", "status", "target", "principal", "detail.owner"]
    op: Literal["eq", "ne", "gte", "lte", "ne_field"]
    value: str | int

    @model_validator(mode="after")
    def valid_operand(self) -> Condition:
        if self.op == "ne_field" and self.value not in FIELDS:
            raise ValueError("unknown comparison field")
        if self.op in {"gte", "lte"} and type(self.value) is not int:
            raise ValueError("numeric operand required")
        if len(str(self.value)) > 200:
            raise ValueError("operand too long")
        return self


class RuleTest(Arguments):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    conditions: list[Condition] = Field(min_length=1, max_length=8)
    positive_ids: list[int] = Field(min_length=1, max_length=50)
    negative_ids: list[int] = Field(min_length=1, max_length=50)


class Publish(Arguments):
    test_id: str = Field(pattern=r"^test-[a-f0-9]{24}$")
    expected_version: int = Field(ge=0)


class Rollback(Arguments):
    rule_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    version: int = Field(ge=1)
    expected_version: int = Field(ge=1)


def field_value(event: dict[str, Any], field: str) -> Any:
    return event.get("detail", {}).get("owner") if field == "detail.owner" else event.get(field)


def matches(event: dict[str, Any], conditions: list[dict[str, Any]]) -> bool:
    for c in conditions:
        left = field_value(event, c["field"])
        right = field_value(event, c["value"]) if c["op"] == "ne_field" else c["value"]
        if left is None or right is None:
            return False
        if c["op"] == "eq" and left != right:
            return False
        if c["op"] in {"ne", "ne_field"} and left == right:
            return False
        if c["op"] in {"gte", "lte"}:
            if type(left) is not int or type(right) is not int:
                return False
            if (c["op"] == "gte" and left < right) or (c["op"] == "lte" and left > right):
                return False
    return True


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def artifact(world: World, artifact_id: str) -> dict[str, Any]:
    item = world.store.get("artifacts", artifact_id)
    if item is None or hashlib.sha256(item["text"].encode()).hexdigest() != item["sha256"]:
        raise ValueError("missing or corrupt artifact")
    return dict(item)


def publish(
    world: World, actor: Actor, rule: dict[str, Any], expected_version: int
) -> dict[str, Any]:
    previous = world.store.get("rules", rule["id"], {})
    if previous and previous.get("engine") != "application-v1":
        raise ValueError("legacy rule uses another engine; choose a new id")
    if previous.get("version", 0) != expected_version:
        raise ValueError("stale rule version")
    current = rule | {
        "version": expected_version + 1,
        "author": actor.id,
        "published_tick": world.tick,
    }
    world.store.put("rule-versions", f"{rule['id']}:{current['version']}", current)
    world.store.put("rules", rule["id"], current)
    return current


def execute(world: World, actor: Actor, action: Action) -> tuple[int, dict[str, Any], str]:
    tool, raw = action.tool, action.args
    if tool == "capture_artifact":
        request = Capture.model_validate(raw)
        case = world._case({"case_id": request.case_id})
        events = case["evidence"]
        if request.kind in {"document", "job"}:
            if request.target not in {e["target"] for e in events}:
                raise ValueError("target not in evidence")
            data = world.store.get(
                "documents" if request.kind == "document" else "jobs", request.target
            )
        elif request.kind == "identity":
            if request.target not in {e["principal"] for e in events}:
                raise ValueError("principal not in evidence")
            data = {
                "principal": request.target,
                "session": world.store.get("sessions", request.target, {}),
                "blocked": world._blocked(request.target),
            }
        elif request.kind == "service":
            data = world.store.get("service", "state")
        else:
            data = events
        if data is None:
            raise ValueError("resource no longer exists; record missing artifact")
        text = encoded(data)
        if len(text.encode()) > 256000:
            raise ValueError("artifact exceeds application snapshot size limit")
        digest = hashlib.sha256(text.encode()).hexdigest()
        aid = (
            "artifact-"
            + hashlib.sha256(
                encoded([case["id"], request.kind, request.target, digest]).encode()
            ).hexdigest()[:24]
        )
        saved = world.store.get("artifacts", aid)
        if saved is None:
            saved = {
                "id": aid,
                "case_id": case["id"],
                "kind": request.kind,
                "target": request.target,
                "text": text,
                "sha256": digest,
                "bytes": len(text.encode()),
                "collected_tick": world.tick,
                "collected_by": actor.id,
                "evidence_ids": case["evidence_ids"],
                "scope": "application_snapshot",
            }
            world.store.put("artifacts", aid, saved)
        return 201, {"artifact": {k: v for k, v in saved.items() if k != "text"}}, aid
    if tool in {"read_artifact", "analyze_artifact"}:
        request_ref = (ArtifactPage if tool == "read_artifact" else Analyze).model_validate(raw)
        item = artifact(world, request_ref.artifact_id)
        if isinstance(request_ref, ArtifactPage):
            end = request_ref.offset + request_ref.limit
            return (
                200,
                {
                    "text": item["text"][request_ref.offset : end],
                    "sha256": item["sha256"],
                    "next_offset": min(end, len(item["text"])),
                    "has_more": end < len(item["text"]),
                },
                item["id"],
            )
        if request_ref.engine != "builtin":
            return (
                409,
                {
                    "error": "Native engine adapter is not configured; no analysis was run.",
                    "engine": request_ref.engine,
                    "artifact_id": item["id"],
                },
                item["id"],
            )
        analysis = {
            "artifact_id": item["id"],
            "engine": "application-json-v1",
            "sha256": item["sha256"],
            "bytes": item["bytes"],
            "kind": item["kind"],
            "format": "JSON",
            "observed_urls": sorted(set(re.findall(r'https?://[^\s"<>]+', item["text"])))[:50],
            "verdict": "not_assessed",
            "limitations": "Static application JSON only; no execution, disassembly or malware verdict.",
        }
        world.store.put(
            "artifact-analysis", item["id"], analysis | {"by": actor.id, "tick": world.tick}
        )
        return 200, {"analysis": analysis}, item["id"]
    if tool == "telemetry_health":
        Arguments.model_validate(raw)
        row = world.store.db.execute(
            "SELECT count(*),min(id),max(id),min(tick),max(tick) FROM events"
        ).fetchone()
        sources = [
            dict(r)
            for r in world.store.db.execute(
                "SELECT tool, count(*) AS events, max(tick) AS last_tick, sum(status>=400) AS errors FROM events GROUP BY tool"
            )
        ]
        return (
            200,
            {
                "retained_events": row[0],
                "first_id": row[1],
                "last_id": row[2],
                "first_tick": row[3],
                "last_tick": row[4],
                "sources": sources,
                "retention_truncated": bool(row[1] and row[1] > 1),
                "adapters": {
                    "application": "available",
                    **{n: "not_configured" for n in NATIVE_ENGINES},
                },
                "limitations": "No expected-rate baseline; source silence alone does not establish log loss.",
            },
            "telemetry",
        )
    if tool == "verify_recovery":
        ref = CaseRef.model_validate(raw)
        case = world._case(ref.model_dump())
        responses = [r for r in case["responses"] if r["verified"]]
        since = max((r["tick"] for r in responses), default=world.tick)
        client_principals = [
            world.principals[a.id] for a in world.actors.values() if a.team == "client"
        ]
        affected = set()
        for event in case["evidence"]:
            if event["tool"] == "disrupt":
                affected.update(client_principals)
            affected.update(
                p
                for p in (event["principal"], event.get("detail", {}).get("owner"))
                if p in client_principals
            )
        client_events: list[dict[str, Any]] = []
        for principal in client_principals:
            client_events.extend(
                e
                for e in world.store.events(through_tick=world.tick, principal=principal, limit=100)
                if e["tick"] > since
                and e["tool"] in {"read_document", "write_document", "call_app"}
                and e["status"] < 400
            )
        result = {
            "case_id": case["id"],
            "checked_tick": world.tick,
            "service_available": world.store.get("service", "state")["down_until"] <= world.tick,
            "mitigation_active": bool(responses) and world._mitigation_active(case),
            "restricted_clients": [p for p in client_principals if world._blocked(p)],
            "client_work_observed": all(
                any(e["principal"] == p for e in client_events) for p in affected
            )
            if affected
            else None,
            "affected_clients": sorted(affected),
            "evidence_ids": [e["id"] for e in client_events if e["principal"] in affected][-50:],
            "integrity": "not_measured",
            "scope": "application_lab; observations do not prove full OS/data recovery",
        }
        world.store.put("recovery-checks", case["id"], result)
        return 200, {"recovery": result}, case["id"]
    if tool == "test_rule":
        test = RuleTest.model_validate(raw)
        if set(test.positive_ids) & set(test.negative_ids):
            raise ValueError("positive/negative sets overlap")
        positives = evidence(world, test.positive_ids, world.tick)
        negatives = evidence(world, test.negative_ids, world.tick)
        conditions = [c.model_dump() for c in test.conditions]
        tp = sum(matches(e, conditions) for e in positives)
        fp = sum(matches(e, conditions) for e in negatives)
        result = {"tp": tp, "fp": fp, "fn": len(positives) - tp, "tn": len(negatives) - fp}
        tid = "test-" + hashlib.sha256(encoded(test.model_dump()).encode()).hexdigest()[:24]
        saved = {
            "id": tid,
            "rule": {"id": test.rule_id, "engine": "application-v1", "conditions": conditions},
            "result": result,
            "positive_ids": sorted(set(test.positive_ids)),
            "negative_ids": sorted(set(test.negative_ids)),
            "label_source": "caller_supplied_not_gold",
            "by": actor.id,
            "tick": world.tick,
        }
        world.store.put("rule-tests", tid, saved)
        return 200, {"test": saved}, tid
    if tool == "publish_rule":
        publication = Publish.model_validate(raw)
        test_run = world.store.get("rule-tests", publication.test_id)
        if test_run is None or test_run["result"]["fp"] or test_run["result"]["fn"]:
            return (
                409,
                {"error": "Tested positive/negative corpus without FP/FN required."},
                publication.test_id,
            )
        current = publish(
            world,
            actor,
            test_run["rule"] | {"test_id": test_run["id"]},
            publication.expected_version,
        )
        return 201, {"rule": current}, current["id"]
    if tool == "rollback_rule":
        rollback = Rollback.model_validate(raw)
        old = world.store.get("rule-versions", f"{rollback.rule_id}:{rollback.version}")
        if old is None:
            raise ValueError("unknown published version")
        current = publish(
            world, actor, old | {"restored_from": rollback.version}, rollback.expected_version
        )
        return 200, {"rule": current}, current["id"]
    raise ValueError("unknown lab evidence tool")
