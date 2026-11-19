"""Map a staging dispatcher port onto plan-then-execute and V4.1 presets.

The production dispatcher is the external OneHost unit ``nox-dispatcher.service``.
This module does not submit jobs to it, does not edit repair policy, and does
not spawn a second scheduler. When a telemetry snapshot is supplied, the
existing read-only ``nox_dispatcher_advisor.assess`` decides HOLD. Safety and
hold advice skip tool execution.

``plan_then_execute`` is the only reasoning loop called here. Reflexion, ReAct,
Tree-of-Thoughts and self-consistency stay in the unpacked package, unwired.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from ._path import ensure_mind_package_on_path

ensure_mind_package_on_path()

from nox_mind_v41.control import PRESETS, request_body
from nox_mind_v41.reflection import plan_then_execute

from .protocols import StagingDisabled, resolve_enabled

_BLOCKING_URGENCY = {"safety", "hold"}
_BLOCKING_CODES = {"STOP_ACTIVE", "S03_NOT_VERIFIED"}


def _load_assess():
    path = Path(__file__).resolve().parents[2] / "nox-control" / "nox_dispatcher_advisor.py"
    spec = importlib.util.spec_from_file_location("nox_dispatcher_advisor_staging_view", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load read-only dispatcher advisor from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assess


_assess = _load_assess()


class DispatcherPlanAdapter:
    """DispatcherPort over an injected llm and an injected tool dict.

    Tools run only when the caller enables the adapter and advisor evidence,
    if any, does not demand safety or hold. Results stay in ``admissions``.
    They are not posted to a host.
    """

    def __init__(self, llm, tools, *, enabled: bool | None = None, max_steps: int = 8, graph=None):
        if not callable(llm):
            raise TypeError("llm must be callable")
        if not isinstance(tools, dict):
            raise TypeError("tools must be a dict")
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps
        self.graph = graph
        self.enabled = resolve_enabled(enabled)
        self.admissions: list[dict] = []

    def submit_goal(self, goal: str, preset: str = "tool_agent", **opts) -> dict:
        return self.submit(goal, preset=preset, snapshot=opts.get("snapshot"), task_id=opts.get("task_id"))

    def submit(self, goal: str, preset: str = "tool_agent", snapshot=None, task_id: str | None = None) -> dict:
        self._guard()
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset}")
        hold = self._hold_reason(snapshot)
        if hold is not None:
            record = {
                "status": "HOLD",
                "executed": False,
                "preset": preset,
                "goal": goal,
                "reason": hold,
                "submitted_to_host": False,
            }
            self.admissions.append(record)
            return record
        body = request_body(preset, [{"role": "user", "content": goal}])
        checkpoint = None
        if self.graph is not None and task_id:
            graph = self.graph

            def checkpoint(step, state, _task=task_id, _graph=graph):
                _graph.checkpoint(_task, step, state)

        planned = plan_then_execute(self.llm, goal, self.tools, max_steps=self.max_steps, checkpoint=checkpoint)
        record = {
            "status": "STAGED",
            "executed": True,
            "preset": preset,
            "goal": goal,
            "request": body,
            "plan": planned["plan"],
            "results": planned["results"],
            "submitted_to_host": False,
        }
        self.admissions.append(record)
        return record

    def _hold_reason(self, snapshot):
        if snapshot is None:
            return None
        advice = _assess(snapshot)
        blocking = [item for item in advice if item.get("urgency") in _BLOCKING_URGENCY or item.get("code") in _BLOCKING_CODES]
        if not blocking:
            return None
        return {"advice": blocking}

    def _guard(self) -> None:
        if not self.enabled:
            raise StagingDisabled(
                "NOX_MIND_V41_STAGING is off; dispatcher adapter did not plan or call tools"
            )
