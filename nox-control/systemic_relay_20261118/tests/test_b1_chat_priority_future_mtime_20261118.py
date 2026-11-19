"""Focused regression: owner chat always wins when activity mtime is in the future.

Load only the pure function from the pinned dispatcher file: importing the full
native dispatcher would require a running NOX host and must not occur in CI.
"""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "runtime" / "owner_subagent_dispatcher.py"


def load_chat_priority(root):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "chat_priority_active"
    ]
    if len(matches) != 1:
        raise AssertionError("HOLD_CHAT_PRIORITY_SOURCE_SHAPE")
    isolated = ast.fix_missing_locations(ast.Module(body=matches, type_ignores=[]))
    namespace = {"ROOT": root, "time": time}
    exec(compile(isolated, str(SOURCE), "exec"), namespace)
    return namespace["chat_priority_active"]



def load_bound_admission(*, chat_active=False, stop=False, project_allowed=True):
    """Extract the real bound admission callback without importing live modules."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    binders = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "bind_dispatcher"
    ]
    if len(binders) != 1:
        raise AssertionError("HOLD_NATIVE_BINDER_SOURCE_SHAPE")
    matches = [
        node for node in binders[0].body
        if isinstance(node, ast.FunctionDef) and node.name == "admission"
    ]
    if len(matches) != 1:
        raise AssertionError("HOLD_NATIVE_ADMISSION_SOURCE_SHAPE")
    isolated = ast.fix_missing_locations(ast.Module(body=matches, type_ignores=[]))
    namespace = {
        "HANDLER": "review", "LEAF_HANDLER": "leaf",
        "PROJECT_HANDLER": "project",
        "chat_priority_active": lambda: chat_active,
        "native": SimpleNamespace(
            stop_active=lambda: stop,
            projects=SimpleNamespace(admitted=lambda _: project_allowed)),
        "old_admission": lambda _: True,
    }
    exec(compile(isolated, str(SOURCE), "exec"), namespace)
    return namespace["admission"]

def load_fresh_native_gate(*, chat_active=False):
    """Extract the actual last-moment gate; no dispatcher import or host I/O."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    native = [node for node in tree.body
              if isinstance(node, ast.ClassDef) and node.name == "Native"]
    if len(native) != 1:
        raise AssertionError("HOLD_NATIVE_SOURCE_SHAPE")
    methods = [node for node in native[0].body
               if isinstance(node, ast.FunctionDef)
               and node.name == "_fresh_admission_reason"]
    if len(methods) != 1:
        raise AssertionError("HOLD_FRESH_ADMISSION_SOURCE_SHAPE")
    isolated = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
    namespace = {
        "chat_priority_active": lambda: chat_active,
        "resource_wait_reason": lambda snapshot: snapshot["reason"],
        "autonomy": SimpleNamespace(AutoHold=RuntimeError),
        "GateError": RuntimeError,
    }
    exec(compile(isolated, str(SOURCE), "exec"), namespace)
    calls = []
    native_state = SimpleNamespace(
        _pool_recovery_uncertain=False,
        read_resource_snapshot=lambda leaf_only=False:
            (calls.append(leaf_only) or {"reason": None}),
    )
    return namespace["_fresh_admission_reason"], native_state, calls


class ChatPriorityFutureMtimeTests(unittest.TestCase):
    def test_chat_priority_blocks_all_native_handlers_at_admission(self):
        # Old code blocked only "review"; "leaf" and "project" were admitted.
        waiting = load_bound_admission(chat_active=True)
        for kind in ("review", "leaf", "project"):
            with self.subTest(handler=kind):
                self.assertFalse(waiting({"handler": kind}))

        unblocked = load_bound_admission(chat_active=False)
        for kind in ("review", "leaf", "project"):
            with self.subTest(handler=kind):
                self.assertTrue(unblocked({"handler": kind}))

        self.assertFalse(load_bound_admission(stop=True)({"handler": "leaf"}))
        self.assertFalse(load_bound_admission(stop=True)({"handler": "review"}))
        self.assertFalse(load_bound_admission(stop=True)({"handler": "project"}))
        self.assertFalse(load_bound_admission(project_allowed=False)({"handler": "project"}))

    def test_chat_started_after_admission_blocks_final_cpu_submit(self):
        # A chat starting between scheduler admission and worker submit must
        # block CPU-only leaf/project work without touching resource/IPC state.
        blocked, owner, calls = load_fresh_native_gate(chat_active=True)
        self.assertEqual(blocked(owner, leaf_only=True), "HOLD_NATIVE_CHAT_PRIORITY")
        self.assertEqual(blocked(owner, leaf_only=False), "HOLD_NATIVE_CHAT_PRIORITY")
        self.assertEqual(calls, [], "no worker resource snapshot during chat")
        allowed, owner, calls = load_fresh_native_gate(chat_active=False)
        self.assertIsNone(allowed(owner, leaf_only=True))
        self.assertEqual(calls, [True])

    def test_marker_absent_is_inactive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            self.assertFalse(load_chat_priority(root)())

    def test_recent_future_and_stale_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            marker = root / "state" / "chat_active"
            marker.touch()
            active = load_chat_priority(root)
            with patch.object(time, "time", return_value=100_000_000):
                os.utime(marker, (99_999_999, 99_999_999))
                self.assertTrue(active(), "recent activity must yield to chat")
                os.utime(marker, (100_000_050, 100_000_050))
                self.assertTrue(active(), "future-dated activity must fail closed")
                os.utime(marker, (99_999_990, 99_999_990))
                self.assertFalse(active(), "stale activity must not block native work")

    def test_symlink_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "state" / "chat_active").symlink_to("missing")
            self.assertTrue(load_chat_priority(root)())


if __name__ == "__main__":
    unittest.main()
