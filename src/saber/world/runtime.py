"""Resumable multi-agent scheduler; slow LLM calls never stop client activity."""

from __future__ import annotations

import importlib
import json
import logging
import os
import queue
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, BinaryIO

from saber.agents.provider import LLMProvider
from saber.agents.skill_library import load_reference_library
from saber.agents.skills import load_playbook
from saber.agents.specialties import BLUE_SKILLS
from saber.domain.errors import BudgetExceeded, IntegrationBlocked
from saber.population.office import OfficeEmitter
from saber.world import learning, work
from saber.world.agents import PLAYBOOKS, baseline, llm_messages, parse_plan
from saber.world.environment import World
from saber.world.learning_worker import Learner
from saber.world.models import Action, Actor, WorldConfig, specialties_for
from saber.world.native import NativeExecutor
from saber.world.office import deployment_profile, snapshot
from saber.world.quota import TeamQuotaProvider
from saber.world.service import LabServer
from saber.world.store import Store


class WorldLock(AbstractContextManager["WorldLock"]):
    """OS-owned advisory lock, released automatically after crashes on Windows/Linux."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "runner.lock"
        self.file: BinaryIO | None = None

    def __enter__(self) -> WorldLock:
        try:
            self.file = self.path.open("a+b")
            if self.path.stat().st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                msvcrt = importlib.import_module("msvcrt")

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if self.file is not None:
                self.file.close()
            self.file = None
            raise RuntimeError("This world is already running; use another directory.") from None
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.file is None:
            return
        try:
            self.file.seek(0)
            if os.name == "nt":
                msvcrt = importlib.import_module("msvcrt")

                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()


class Planner:
    """A bounded inference queue; QuotaProvider reserves usage transactionally."""

    def __init__(self, provider: LLMProvider, actors: int, workers: int = 4) -> None:
        self.provider = provider
        self.requests: queue.Queue[tuple[Actor, dict[str, Any], dict[str, Any] | None]] = (
            queue.Queue(maxsize=actors)
        )
        self.results: queue.Queue[tuple[str, list[Action], str, int, int]] = queue.Queue(
            maxsize=actors
        )
        self.pending: set[str] = set()
        self.stopping = threading.Event()
        self.exhausted = False
        self.threads = [
            threading.Thread(target=self._work, daemon=True, name=f"saber-world-planner-{i}")
            for i in range(min(workers, actors))
        ]
        for thread in self.threads:
            thread.start()

    def request(
        self, actor: Actor, obs: dict[str, Any], pinned: dict[str, Any] | None = None
    ) -> None:
        if actor.id in self.pending or self.exhausted or self.stopping.is_set():
            return
        self.pending.add(actor.id)
        self.requests.put_nowait((actor, obs, pinned))

    def _work(self) -> None:
        while not self.stopping.is_set():
            try:
                actor, obs, pinned = self.requests.get(timeout=0.1)
            except queue.Empty:
                continue
            if self.stopping.is_set():
                break
            try:
                if self.exhausted:
                    raise BudgetExceeded("Persistent LLM budget exhausted.")
                if isinstance(self.provider, TeamQuotaProvider):
                    response = self.provider.generate_for(
                        actor.team,
                        llm_messages(actor, obs, pinned=pinned),
                        max_tokens=1024,
                        should_stop=self.stopping.is_set,
                    )
                else:
                    response = self.provider.generate(
                        llm_messages(actor, obs, pinned=pinned), max_tokens=1024
                    )
                actions, note = parse_plan(actor, response.text)
            except BudgetExceeded:
                self.exhausted = True
                actions, note = [], "LLM budget exhausted; scripted fallback."
            except IntegrationBlocked:
                actions, note = [], "LLM unavailable/quota resting; scripted fallback."
            except Exception:
                actions, note = [], "LLM failure; scripted fallback (error details redacted)."
            if not self.stopping.is_set():
                self.results.put(
                    (
                        actor.id,
                        actions,
                        note,
                        int(obs["tick"]),
                        int(obs.get("control", {}).get("generation", 0)),
                    )
                )

    def close(self) -> None:
        self.stopping.set()
        # An in-flight network call may take up to the transport timeout. Keep its store
        # alive until it finishes; no new inference is submitted after shutdown.
        deadline = time.monotonic() + 65
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))


def atomic_json(path: Path, obj: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


class Runner:
    def __init__(
        self,
        store: Store,
        config: WorldConfig,
        *,
        provider: LLMProvider | None = None,
        emitter: OfficeEmitter | None = None,
    ) -> None:
        self.store, self.config = store, config
        if config.execution_mode == "range":
            raise ValueError("SOC range execution uses 'saber lab' deployments, not 'world run'.")
        if provider is not None:
            for skill in {
                PLAYBOOKS[a.team if a.team == "client" else a.role] for a in config.actors
            } | {BLUE_SKILLS[s] for a in config.actors for s in specialties_for(a)}:
                load_playbook(skill, mode="world")
        libraries = {
            BLUE_SKILLS[s]: load_reference_library(BLUE_SKILLS[s])
            for a in config.actors
            for s in specialties_for(a)
        }
        self.world = World(store, config)
        learning.initialize(
            self.world,
            {
                skill: load_playbook(skill, mode="world")
                for skill in {
                    PLAYBOOKS[a.team if a.team == "client" else a.role] for a in config.actors
                }
                | {BLUE_SKILLS[s] for a in config.actors for s in specialties_for(a)}
            },
            reference_libraries=libraries,
        )
        with store.transaction():
            store.put("meta", "engine", "hybrid" if provider else "scripted")
            store.put(
                "meta",
                "llm_key_layout",
                "teams"
                if isinstance(provider, TeamQuotaProvider)
                else "shared"
                if provider
                else "off",
            )
        self.server = LabServer(self.world)
        self.emitter = emitter or OfficeEmitter()
        self.planner = (
            Planner(provider, len(config.actors), config.llm_workers)
            if provider is not None
            else None
        )
        self._closed = False
        self.run_id = uuid.uuid4().hex
        self.profile = deployment_profile(store.root)
        self.telemetry = RotatingFileHandler(
            store.root / "access.jsonl", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        self.server.start()
        self.native = NativeExecutor(store) if config.execution_mode == "native" else None
        self.clients = {a.id: self.server.client(a.id) for a in config.actors}
        atomic_json(
            store.root / "runtime.json",
            {
                "url": self.server.url,
                "pid": os.getpid(),
                "status": "running",
                "authentication": "per-agent bearer capabilities; not exported",
            },
        )
        self._publish_office(self.world.report())
        self.learner = (
            Learner(self.world, provider) if provider and config.learning_enabled else None
        )

    def _publish_office(self, report: dict[str, Any]) -> None:
        atomic_json(
            self.store.root / "learning.json",
            learning.summary(self.store)
            | {
                "tick": self.world.tick,
                "released_versions": self.store.items("skill-heads"),
                "active_epoch": self.store.get("learning-meta", "epoch", {}),
                "enabled": self.config.learning_enabled,
            },
        )
        event = snapshot(
            self.store,
            self.config,
            report,
            run_id=self.run_id,
            profile=self.profile,
            pending=set(self.planner.pending) if self.planner else set(),
            stopped=self._closed,
            budget_exhausted=bool(self.planner and self.planner.exhausted),
        )
        atomic_json(self.store.root / "office.json", event)
        self.emitter.world_snapshot(event)

    def _plans(self) -> None:
        if self.planner is None:
            return
        while True:
            try:
                aid, actions, note, at, generation = self.planner.results.get_nowait()
            except queue.Empty:
                break
            self.planner.pending.discard(aid)
            # Drop stale decisions rather than executing against an unrelated world state.
            fresh = self.world.tick - at <= self.config.profile_refresh_ticks
            with self.store.transaction():
                current = work.control(self.world, aid)
                if (
                    not fresh
                    or current["status"] != "ACTIVE"
                    or current["generation"] != generation
                ):
                    self.world._metric("discarded_plans", 1)
                    continue
                self.store.put("plans", aid, [a.model_dump() for a in actions] if fresh else [])
                memory = self.store.get("memory", aid, {})
                memory.update(
                    {
                        "note": note if fresh else "Expired LLM plan discarded.",
                        "planned_at": at,
                        "plan_source": "llm" if actions and fresh else "scripted-fallback",
                    }
                )
                self.store.put("memory", aid, memory)

    def step(self) -> dict[str, Any]:
        self._plans()
        tick = self.world.advance()
        with self.store.transaction():
            learning.activate(self.world)
        # Rotate start order so fixed role ordering does not give one team permanent advantage.
        actors = self.config.actors
        offset = (tick + self.config.seed) % len(actors)
        for actor in actors[offset:] + actors[:offset]:
            with self.store.transaction():
                control = work.control(self.world, actor.id)
                if control["status"] == "WAITING" and tick >= control["until_tick"]:
                    work.set_control(self.world, actor.id, "ACTIVE", "Wait completed.")
                    control = work.control(self.world, actor.id)
            if control["status"] != "ACTIVE":
                continue
            if tick % actor.interval_ticks or (
                actor.team == "red" and tick < self.config.red_start_tick
            ):
                continue
            client = self.clients[actor.id]
            obs = client.observe()
            memory = self.store.get("memory", actor.id, {})
            turns = int(memory.get("turns", 0))
            if self.planner is not None and tick >= int(memory.get("next_plan", 0)):
                self.planner.request(
                    actor,
                    obs,
                    learning.prompt_version(self.store, learning.actor_skill(self.world, actor)),
                )
                memory["next_plan"] = tick + self.config.profile_refresh_ticks
                with self.store.transaction():
                    self.store.put("memory", actor.id, memory)
            plan = self.store.get("plans", actor.id, [])
            source = "llm" if plan else ("scripted-fallback" if self.planner else "scripted")
            chosen = Action.model_validate(plan.pop(0)) if plan else baseline(actor, obs, turns)
            result = (
                self.server.native_act(self.native, actor.id, tick, chosen)
                if self.native
                else client.act(chosen)
            )
            # Persist a bounded private agent journal; never expose other teams' plans.
            with self.store.transaction():
                if work.control(self.world, actor.id)["generation"] != control["generation"]:
                    plan = []
                memory = self.store.get("memory", actor.id, memory)
                memory.update(
                    {
                        "turns": turns + 1,
                        "last_tool": chosen.tool,
                        "last_tick": tick,
                        "last_status": result.get("status"),
                        "source": source,
                    }
                )
                self.store.put("memory", actor.id, memory)
                self.store.put("plans", actor.id, plan)
                journal = self.store.get("journals", actor.id, [])
                journal.append(
                    {
                        "tick": tick,
                        "action": chosen.model_dump(),
                        "event_id": result.get("event_id"),
                        "source": source,
                    }
                )
                self.store.put("journals", actor.id, journal[-100:])
                self.world._metric("actions_" + source.replace("-", "_"), 1)
        if self.learner:
            self.learner.poll()
        report = self.world.report()
        cursor = int(self.store.get("meta", "telemetry_cursor", 0))
        events = self.store.events(after=cursor, through_tick=tick, limit=2000)
        for event in events:
            record = logging.LogRecord(
                "saber.world", logging.INFO, "", 0, json.dumps(event, ensure_ascii=False), (), None
            )
            self.telemetry.emit(record)
        if events:
            with self.store.transaction():
                self.store.put("meta", "telemetry_cursor", events[-1]["id"])
        atomic_json(self.store.root / "report.json", report)
        self._publish_office(report)
        if tick % 20 == 0:
            self.store.archive(self.config.retention_events, self.config.archive_bytes)
            self.store.checkpoint()
        return report

    def run(
        self,
        *,
        ticks: int | None = None,
        stop_file: Path | None = None,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> dict[str, Any]:
        stop_file = stop_file or self.store.root / "STOP"
        completed = 0
        reason = "tick_limit"
        try:
            while ticks is None or completed < ticks:
                if stop_file.exists():
                    reason = "stop_file"
                    break
                if self.store.disk_bytes() >= self.config.disk_budget_bytes:
                    reason = "disk_budget"
                    break
                start = time.monotonic()
                report = self.step()
                completed += 1
                if on_tick:
                    on_tick(report)
                if ticks is None or completed < ticks:
                    remaining = max(0.0, self.config.tick_seconds - (time.monotonic() - start))
                    # Respond to STOP without waiting out a long configured tick interval.
                    while remaining > 0 and not stop_file.exists():
                        part = min(remaining, 0.2)
                        sleep(part)
                        remaining -= part
        except KeyboardInterrupt:
            reason = "interrupted"
        except Exception:
            reason = "error"
            atomic_json(
                self.store.root / "report.json", self.world.report() | {"stop_reason": "error"}
            )
            raise
        finally:
            try:
                with self.store.transaction():
                    for actor in self.config.actors:
                        learning.seal(self.world, actor, "run_end")
                # Only a normal finite run drains work. STOP/Ctrl+C do not start more calls.
                if reason == "tick_limit" and self.learner:
                    self.learner.flush()
            finally:
                self.close()
        report = self.world.report() | {"stop_reason": reason}
        atomic_json(self.store.root / "report.json", report)
        return report

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.learner:
            self.learner.stopping.set()
        if self.planner:
            self.planner.close()
        if self.learner:
            self.learner.close()
        self.server.close()
        if self.native:
            self.native.close()
        self.telemetry.close()
        self.store.checkpoint()
        atomic_json(self.store.root / "runtime.json", {"status": "stopped", "pid": os.getpid()})
        self._publish_office(self.world.report())
