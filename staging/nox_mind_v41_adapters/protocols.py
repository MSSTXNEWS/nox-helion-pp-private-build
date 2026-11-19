"""Minimal ports for the NOX mind v4.1 staging layer.

This repository does not contain a callable S03 memory API, a dispatcher
job-submission API, or CoreID / PersonaID types. The names below are staging
stand-ins. They are not wired to:

- ``memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3`` (host path only;
  the in-repo reader expects ``knowledge(content, teacher, content_sha)`` and
  opens it read-only on a machine path that is not in this checkout)
- the OneHost unit ``nox-dispatcher.service``
- any production identity object

``InMemoryS03``, ``InMemoryDispatcher`` and ``InMemoryIdentity`` are fakes for
tests. They do not open sockets, spawn processes, or write a database file.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


_ON = {"1", "true", "yes", "on"}


class StagingDisabled(RuntimeError):
    """Adapter called while the default-off staging flag is off.

    Nothing was written to memory, the dispatcher, or a persona cache.
    """


class StagingRefused(RuntimeError):
    """Staging helper refused a path that belongs to host S03."""


def resolve_enabled(enabled: bool | None) -> bool:
    """Explicit argument wins. ``None`` reads ``NOX_MIND_V41_STAGING``.

    Unset or any value other than 1/true/yes/on is off. No production module
    calls this function.
    """
    if enabled is not None:
        return bool(enabled)
    return os.environ.get("NOX_MIND_V41_STAGING", "").strip().lower() in _ON


@runtime_checkable
class S03MemoryPort(Protocol):
    def read(self, persona_id: str, query: str, **opts): ...

    def write(self, persona_id: str, text: str, **meta): ...


@runtime_checkable
class DispatcherPort(Protocol):
    def submit_goal(self, goal: str, preset: str = "tool_agent", **opts): ...


@runtime_checkable
class IdentityPort(Protocol):
    def current_ids(self): ...

    def switch_persona(self, persona_id: str): ...


class InMemoryS03:
    """Fake S03 read/write port. Not the host ``knowledge`` table."""

    def __init__(self):
        self.rows: list[dict] = []

    def write(self, persona_id: str, text: str, **meta) -> str:
        rec = {"id": str(len(self.rows) + 1), "persona_id": persona_id, "text": text, **meta}
        self.rows.append(rec)
        return rec["id"]

    def read(self, persona_id: str, query: str, **opts) -> list:
        needle = query.lower()
        return [r for r in self.rows if r["persona_id"] == persona_id and needle in r["text"].lower()]


class InMemoryDispatcher:
    """Fake dispatcher admission log. ``submitted`` stays false: nothing is sent."""

    def __init__(self):
        self.jobs: list[dict] = []

    def submit_goal(self, goal: str, preset: str = "tool_agent", **opts) -> dict:
        job = {
            "id": f"job-{len(self.jobs) + 1}",
            "goal": goal,
            "preset": preset,
            "opts": dict(opts),
            "submitted": False,
        }
        self.jobs.append(job)
        return job


class InMemoryIdentity:
    """Fake CoreID + PersonaID binding. Neither identifier exists in this repo."""

    def __init__(self, core_id: str = "core-unset", persona_id: str = "persona-unset"):
        self.core_id = core_id
        self.persona_id = persona_id

    def current_ids(self):
        return (self.core_id, self.persona_id)

    def switch_persona(self, persona_id: str):
        self.persona_id = persona_id
