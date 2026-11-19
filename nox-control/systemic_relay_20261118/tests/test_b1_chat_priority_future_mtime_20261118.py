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

    def test_chat_start_during_pool_boot_prevents_leaf_submit(self):
        # Exercise the actual leaf handler.  Initial resource admission passes;
        # process start/readback then exposes a new owner chat at the last fence.
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == "Native")
        method = next(node for node in native.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_handle_leaf")
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        scope = {"LEAF_HANDLER": "leaf", "ROLES": ("runtime", "memory", "weights"),
                 "time": time, "sqlite3": sqlite3, "GateError": RuntimeError}
        exec(compile(module, str(SOURCE), "exec"), scope)
        calls, submissions = [], []
        task = {
            "id": "B1-CPU-SUBMIT-TEST", "handler": "leaf", "queue_id": "queue-1",
            "owner_claim": {"nonce": "original-claim"},
            "params": {"operation": "source_read", "parent_task_id": "6V14-03",
                       "source_sha256": "sha-pinned", "job_id": "job-1"},
        }
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            catalog={"tasks": [task]}, source="sha-pinned", pool=None,
            lock=threading.Lock(), interrupted={},
            _claim_current=lambda *a, **k: True,
            stop_active=lambda: False, writer_lease=lambda: True,
            owner_allowed=lambda: True,
            process_readback=lambda: [{"role": "runtime", "pid": 17,
                                       "process_starttime": 999}],
        )
        def gate(*, leaf_only=False):
            calls.append(leaf_only)
            return None if len(calls) == 1 else "HOLD_NATIVE_CHAT_PRIORITY"
        def start_existing_pool(count):
            self.assertEqual(count, 3)
            owner.pool = SimpleNamespace(active={}, submit=lambda _: submissions.append(_))
            return True
        owner._fresh_admission_reason = gate
        owner.ensure_processes = start_existing_pool
        status, reason = scope["_handle_leaf"](owner, task)
        self.assertEqual((status, reason), ("wait", "HOLD_NATIVE_CHAT_PRIORITY"))
        self.assertEqual(calls, [True, True], "fresh resource/chat gate after boot")
        self.assertEqual(submissions, [], "no worker execution after chat begins")
        self.assertEqual(task["owner_claim"]["nonce"], "original-claim")
        self.assertEqual(owner.interrupted, {})

    def test_interrupted_leaf_claim_fails_closed_without_resubmit(self):
        # An earlier STOP/chat teardown may have lost a late result.  Reusing
        # the same claim must not submit again until durable reconciliation.
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == "Native")
        methods = [node for node in native.body
                   if isinstance(node, ast.FunctionDef) and node.name == "_handle_leaf"]
        self.assertEqual(len(methods), 1)
        module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
        scope = {"LEAF_HANDLER": "leaf", "ROLES": ("runtime", "memory", "weights"),
                 "time": time, "sqlite3": sqlite3, "GateError": RuntimeError}
        exec(compile(module, str(SOURCE), "exec"), scope)
        task = {
            "id": "B1-INTERRUPTED-CLAIM", "handler": "leaf", "queue_id": "queue-1",
            "owner_claim": {"nonce": "original-claim"},
            "params": {"operation": "source_read", "parent_task_id": "6V14-03",
                       "source_sha256": "sha-pinned", "job_id": "job-1"},
        }
        marker = "WAIT_OWNER_STOP_OR_CHAT_PRIORITY"
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            catalog={"tasks": [task]}, source="sha-pinned", pool=None,
            lock=threading.Lock(), interrupted={task["id"]: marker},
            _claim_current=lambda *a, **k: True,
            stop_active=lambda: False, writer_lease=lambda: True,
            owner_allowed=lambda: True,
        )
        def forbidden_admission(*args, **kwargs):
            self.fail("uncertain claim must be checked before resource work")
        owner._fresh_admission_reason = forbidden_admission
        for _ in range(2):
            self.assertEqual(scope["_handle_leaf"](owner, task),
                             ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
            self.assertIsNone(owner.pool, "must not start workers or resubmit")
            self.assertEqual(owner.interrupted[task["id"]], marker,
                             "interruption evidence survives repeated admission")

    def test_interrupted_review_claim_fails_closed_without_resubmit(self):
        # A STOP/chat interrupt can arrive after a review worker produced a
        # result. Neither retry nor admission may erase its unsettled marker.
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(node for node in tree.body
                      if isinstance(node, ast.ClassDef) and node.name == "Native")
        methods = [node for node in native.body
                   if isinstance(node, ast.FunctionDef) and node.name == "_handle"]
        self.assertEqual(len(methods), 1)
        module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
        scope = {"HANDLER": "review", "LEAF_HANDLER": "leaf",
                 "PROJECT_HANDLER": "project",
                 "ROLES": ("runtime", "memory", "weights"),
                 "time": time, "sqlite3": sqlite3, "GateError": RuntimeError}
        exec(compile(module, str(SOURCE), "exec"), scope)
        task = {
            "id": "B1-INTERRUPTED-REVIEW", "handler": "review",
            "owner_claim": {"nonce": "original-claim"},
            "params": {"role": "runtime", "policy_sha256": "policy-sha", "job_id": "job-1"},
        }
        marker = "WAIT_OWNER_STOP_OR_CHAT_PRIORITY"
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            projects=None, catalog={"tasks": [task]}, policy={"sha256": "policy-sha"},
            lock=threading.RLock(), interrupted={task["id"]: marker}, pool=None,
            _claim_current=lambda *a, **k: True,
            stop_active=lambda: False, writer_lease=lambda: True,
        )
        def forbidden_admission(*args, **kwargs):
            self.fail("review claim must be reconciled before worker admission")
        owner._fresh_admission_reason = forbidden_admission
        for _ in range(2):
            self.assertEqual(scope["_handle"](owner, task),
                             ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
            self.assertIsNone(owner.pool)
            self.assertEqual(owner.interrupted[task["id"]], marker)

    def test_completed_review_yields_to_new_chat_without_replaying_result(self):
        # Reproduce chat starting AFTER the completed IPC result was removed.
        # Old code returned WAIT but forgot that this claim was already executed.
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                      and x.name == "Native")
        method = next(x for x in native.body if isinstance(x, ast.FunctionDef)
                      and x.name == "_handle")
        scope = {"PROJECT_HANDLER": "project", "LEAF_HANDLER": "leaf",
                 "ROLES": ("runtime", "memory", "weights"),
                 "RECEIPT": "NOX_NATIVE_SUBAGENT_RECEIPT_V1",
                 "sqlite3": sqlite3, "time": time, "GateError": RuntimeError,
                 "autonomy": SimpleNamespace(AutoHold=RuntimeError),
                 "remember": lambda *_: self.fail("unadmitted receipt write")}
        chat_calls = []
        scope["chat_priority_active"] = (
            lambda: chat_calls.append(1) is None and len(chat_calls) >= 2)
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), scope)
        task = {"id": "B1-POSTPOP-REVIEW", "handler": "review",
                "owner_claim": {"nonce": "original-claim"},
                "params": {"role": "runtime", "policy_sha256": "policy-sha",
                           "job_id": "job-1"}, "title": "review"}
        event = {"state": "CANDIDATE_NOT_APPLIED", "pid": 17,
                 "native_observation": {
                     "claim": "original-claim",
                     "policy_ack": {"sha256": "policy-sha", "full_file_read": True},
                     "worker": {"pid": 17}}}
        submissions = []
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            projects=None, catalog={"tasks": [task]}, policy={"sha256": "policy-sha"},
            source="source-sha", lock=threading.RLock(), interrupted={},
            completed={}, _claim_current=lambda *a, **kw: True,
            stop_active=lambda: False, writer_lease=lambda: True,
            _fresh_admission_reason=lambda: None, _drain=lambda: None,
            ns={"owner_mentor": SimpleNamespace(clean=lambda x: x)})
        def submit(_):
            submissions.append(_)
            owner.completed[task["id"]] = event
        owner.pool = SimpleNamespace(submit=submit)
        self.assertEqual(scope["_handle"](owner, task),
                         ("wait", "HOLD_NATIVE_REVIEW_RESULT_UNSETTLED"))
        self.assertEqual(submissions[0]["id"], task["id"])
        self.assertEqual(owner.interrupted[task["id"]],
                         "HOLD_NATIVE_REVIEW_RESULT_UNSETTLED")
        self.assertNotIn(task["id"], owner.completed)
        scope["chat_priority_active"] = lambda: False
        self.assertEqual(scope["_handle"](owner, task),
                         ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
        self.assertEqual(len(submissions), 1, "no second native submission")

    def test_completed_leaf_loses_writer_lease_without_replaying(self):
        # Writer lease can disappear between IPC result pop and S03 admission.
        # The result must remain unsettled even when lease subsequently returns.
        import hashlib
        import json
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                      and x.name == "Native")
        method = next(x for x in native.body if isinstance(x, ast.FunctionDef)
                      and x.name == "_handle_leaf")
        def encoded(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()
        def digest(raw):
            return hashlib.sha256(raw).hexdigest()
        scope = {"LEAF_HANDLER": "leaf", "ROLES": ("runtime", "memory", "weights"),
                 "RECEIPT": "NOX_NATIVE_SUBAGENT_RECEIPT_V1",
                 "sqlite3": sqlite3, "time": time, "GateError": RuntimeError,
                 "encoded": encoded, "digest": digest, "chat_priority_active": lambda: False,
                 "remember": lambda *_: self.fail("lost lease must block S03")}
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), scope)
        task = {
            "id": "B1-POSTPOP-LEAF", "handler": "leaf", "queue_id": "Q1",
            "owner_claim": {"nonce": "original-claim"}, "title": "cpu",
            "params": {"operation": "chat_health", "parent_task_id": "6V14-03",
                       "source_sha256": "source-sha", "job_id": "job-1"}}
        pins = {"source.py": "pinned-sha"}
        leaf = {"worker": {"pid": 17, "process_starttime": 999},
                "check_completed": True, "check_passed": True,
                "original_task_accepted": False, "model_called": False,
                "claim": "original-claim", "operation": "chat_health",
                "parent_task_id": "6V14-03", "queue_id": "Q1",
                "source_sha256": "source-sha", "source_pins": pins}
        event = {"state": "NATIVE_LEAF_COMPLETED", "pid": 17,
                 "leaf_evidence": leaf, "leaf_evidence_sha256": digest(encoded(leaf))}
        leases, submissions = [], []
        def lease():
            leases.append(True)
            return len(leases) != 3
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            catalog={"tasks": [task]}, source="source-sha",
            config={"leaf_source_pins": pins}, lock=threading.RLock(),
            interrupted={}, completed={}, pool=None,
            _claim_current=lambda *a, **kw: True, stop_active=lambda: False,
            writer_lease=lease, owner_allowed=lambda: True,
            _fresh_admission_reason=lambda **_: None,
            process_readback=lambda: [{"role": "runtime", "pid": 17,
                                       "process_starttime": 999}],
            _drain=lambda: None,
            ns={"owner_mentor": SimpleNamespace(clean=lambda x: x)})
        def submit(_):
            submissions.append(_)
            owner.completed[task["id"]] = event
        owner.pool = SimpleNamespace(active={}, submit=submit)
        self.assertEqual(scope["_handle_leaf"](owner, task),
                         ("wait", "HOLD_NATIVE_LEAF_RESULT_UNSETTLED"))
        self.assertEqual(owner.interrupted[task["id"]],
                         "HOLD_NATIVE_LEAF_RESULT_UNSETTLED")
        self.assertNotIn(task["id"], owner.completed)
        self.assertEqual(scope["_handle_leaf"](owner, task),
                         ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
        self.assertEqual(len(submissions), 1, "recovered lease is not replay authority")


    def test_chat_arrives_after_leaf_submit_or_event_pop_no_duplicate(self):
        # Two chat races exercised against the actual AST-extracted leaf handler.
        import hashlib
        import json
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Native")
        method = next(n for n in native.body
                      if isinstance(n, ast.FunctionDef) and n.name == "_handle_leaf")
        def encoded(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()
        def digest(raw):
            return hashlib.sha256(raw).hexdigest()
        for chat_call in (1, 2):
            with self.subTest(chat_call=chat_call):
                seen, submits, closes = [], [], []
                scope = {
                    "LEAF_HANDLER": "leaf", "ROLES": ("runtime", "memory", "weights"),
                    "RECEIPT": "NOX_NATIVE_SUBAGENT_RECEIPT_V1", "sqlite3": sqlite3,
                    "time": time, "GateError": RuntimeError,
                    "encoded": encoded, "digest": digest,
                    "remember": lambda _: self.fail("chat forbids S03 admission"),
                    "chat_priority_active": lambda: (
                        seen.append(1) is None and len(seen) >= chat_call),
                }
                exec(compile(ast.fix_missing_locations(
                    ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), scope)
                task = {
                    "id": "B1-INFLIGHT-CHAT", "handler": "leaf", "queue_id": "Q1",
                    "owner_claim": {"nonce": "original-claim"}, "title": "cpu",
                    "params": {"operation": "chat_health", "parent_task_id": "6V14-03",
                               "source_sha256": "source-sha", "job_id": "job-1"}}
                pins = {"source.py": "pinned-sha"}
                leaf = {"worker": {"pid": 17, "process_starttime": 999},
                        "check_completed": True, "check_passed": True,
                        "original_task_accepted": False, "model_called": False,
                        "claim": "original-claim", "operation": "chat_health",
                        "parent_task_id": "6V14-03", "queue_id": "Q1",
                        "source_sha256": "source-sha", "source_pins": pins}
                event = {"state": "NATIVE_LEAF_COMPLETED", "pid": 17,
                         "leaf_evidence": leaf, "leaf_evidence_sha256": digest(encoded(leaf))}
                owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
                    catalog={"tasks": [task]}, source="source-sha",
                    config={"leaf_source_pins": pins}, lock=threading.RLock(),
                    interrupted={}, completed={}, pool=None,
                    _claim_current=lambda *a, **kw: True, stop_active=lambda: False,
                    writer_lease=lambda: True, owner_allowed=lambda: True,
                    _fresh_admission_reason=lambda **_: None,
                    process_readback=lambda: [
                        {"role": "runtime", "pid": 17, "process_starttime": 999}],
                    _drain=lambda: None,
                    ns={"owner_mentor": SimpleNamespace(clean=lambda x: x)})
                def submit(payload):
                    submits.append(payload)
                    owner.completed[task["id"]] = event
                def close(reason):
                    closes.append(reason)
                    owner.pool = None  # The handler must retain the HOLD itself.
                owner.pool = SimpleNamespace(active={}, submit=submit)
                owner.close_pool = close
                first = scope["_handle_leaf"](owner, task)
                if chat_call == 1:
                    self.assertEqual(first, ("wait", "WAIT_OWNER_CHAT_PRIORITY"))
                    self.assertEqual(closes, ["WAIT_OWNER_CHAT_PRIORITY"])
                    self.assertEqual(owner.interrupted[task["id"]],
                                     "HOLD_NATIVE_LEAF_CHAT_UNSETTLED")
                else:
                    self.assertEqual(first, ("wait", "HOLD_NATIVE_LEAF_RESULT_UNSETTLED"))
                    self.assertEqual(closes, [])
                    self.assertEqual(owner.interrupted[task["id"]],
                                     "HOLD_NATIVE_LEAF_RESULT_UNSETTLED")
                self.assertEqual(len(submits), 1)
                scope["chat_priority_active"] = lambda: False
                self.assertEqual(scope["_handle_leaf"](owner, task),
                                 ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
                self.assertEqual(len(submits), 1)

    def test_review_unknown_s03_commit_never_resubmits_same_claim(self):
        # The S03 writer may commit the receipt and then report a readback error.
        # Retrying the worker after that error would perform the claim twice.
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                      and n.name == "Native")
        method = next(n for n in native.body if isinstance(n, ast.FunctionDef)
                      and n.name == "_handle")
        def uncertain(_):
            raise RuntimeError("HOLD_S03_UNKNOWN_COMMIT")
        scope = {"PROJECT_HANDLER": "project", "LEAF_HANDLER": "leaf",
                 "ROLES": ("runtime", "memory", "weights"),
                 "RECEIPT": "NOX_NATIVE_SUBAGENT_RECEIPT_V1",
                 "sqlite3": sqlite3, "time": time, "GateError": RuntimeError,
                 "autonomy": SimpleNamespace(AutoHold=RuntimeError),
                 "remember": uncertain, "chat_priority_active": lambda: False}
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), scope)
        task = {"id": "B1-REVIEW-UNKNOWN-S03", "handler": "review",
                "owner_claim": {"nonce": "original-claim"},
                "params": {"role": "runtime", "policy_sha256": "policy-sha",
                           "job_id": "job-1"}, "title": "review"}
        event = {"state": "CANDIDATE_NOT_APPLIED", "pid": 17,
                 "native_observation": {
                     "claim": "original-claim",
                     "policy_ack": {"sha256": "policy-sha", "full_file_read": True},
                     "worker": {"pid": 17}}}
        submits = []
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            projects=None, catalog={"tasks": [task]}, policy={"sha256": "policy-sha"},
            source="source-sha", lock=threading.RLock(), interrupted={},
            completed={}, _claim_current=lambda *a, **kw: True,
            stop_active=lambda: False, writer_lease=lambda: True,
            _fresh_admission_reason=lambda: None, _drain=lambda: None,
            ns={"owner_mentor": SimpleNamespace(clean=lambda x: x)})
        def submit(payload):
            submits.append(payload)
            owner.completed[task["id"]] = event
        owner.pool = SimpleNamespace(submit=submit)
        self.assertEqual(scope["_handle"](owner, task),
                         (False, "HOLD_S03_UNKNOWN_COMMIT"))
        self.assertEqual(owner.interrupted[task["id"]],
                         "HOLD_NATIVE_REVIEW_ERROR_UNSETTLED")
        self.assertEqual(scope["_handle"](owner, task),
                         ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
        self.assertEqual(len(submits), 1)

    def test_leaf_unknown_s03_commit_never_resubmits_same_claim(self):
        import hashlib
        import json
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                      and n.name == "Native")
        method = next(n for n in native.body if isinstance(n, ast.FunctionDef)
                      and n.name == "_handle_leaf")
        def encoded(value):
            return json.dumps(value, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":"), allow_nan=False).encode()
        def digest(raw):
            return hashlib.sha256(raw).hexdigest()
        def uncertain(_):
            raise RuntimeError("HOLD_S03_UNKNOWN_COMMIT")
        scope = {"LEAF_HANDLER": "leaf", "ROLES": ("runtime", "memory", "weights"),
                 "RECEIPT": "NOX_NATIVE_SUBAGENT_RECEIPT_V1",
                 "sqlite3": sqlite3, "time": time, "GateError": RuntimeError,
                 "encoded": encoded, "digest": digest,
                 "chat_priority_active": lambda: False, "remember": uncertain}
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), scope)
        task = {"id": "B1-LEAF-UNKNOWN-S03", "handler": "leaf",
                "queue_id": "Q1", "owner_claim": {"nonce": "original-claim"},
                "title": "cpu",
                "params": {"operation": "chat_health", "parent_task_id": "6V14-03",
                           "source_sha256": "source-sha", "job_id": "job-1"}}
        pins = {"source.py": "pinned-sha"}
        leaf = {"worker": {"pid": 17, "process_starttime": 999},
                "check_completed": True, "check_passed": True,
                "original_task_accepted": False, "model_called": False,
                "claim": "original-claim", "operation": "chat_health",
                "parent_task_id": "6V14-03", "queue_id": "Q1",
                "source_sha256": "source-sha", "source_pins": pins}
        event = {"state": "NATIVE_LEAF_COMPLETED", "pid": 17,
                 "leaf_evidence": leaf, "leaf_evidence_sha256": digest(encoded(leaf))}
        submits = []
        owner = SimpleNamespace(_durable_submit_fence=lambda task: None,
            _durable_terminal_fence=lambda task, receipt: None,
            
            catalog={"tasks": [task]}, source="source-sha",
            config={"leaf_source_pins": pins}, lock=threading.RLock(),
            interrupted={}, completed={}, pool=None,
            _claim_current=lambda *a, **kw: True,
            stop_active=lambda: False, writer_lease=lambda: True,
            owner_allowed=lambda: True, _fresh_admission_reason=lambda **_: None,
            process_readback=lambda: [{"role": "runtime", "pid": 17,
                                       "process_starttime": 999}],
            _drain=lambda: None,
            ns={"owner_mentor": SimpleNamespace(clean=lambda x: x)})
        def submit(payload):
            submits.append(payload)
            owner.completed[task["id"]] = event
        owner.pool = SimpleNamespace(active={}, submit=submit)
        self.assertEqual(scope["_handle_leaf"](owner, task),
                         (False, "HOLD_S03_UNKNOWN_COMMIT"))
        self.assertEqual(owner.interrupted[task["id"]],
                         "HOLD_NATIVE_LEAF_ERROR_UNSETTLED")
        self.assertEqual(scope["_handle_leaf"](owner, task),
                         ("wait", "HOLD_NATIVE_INTERRUPTED_UNSETTLED"))
        self.assertEqual(len(submits), 1)

    def test_durable_presubmit_intent_survives_restart_and_blocks_replay(self):
        # Real AST-extracted source method, real JSON on disk, two fresh owner
        # objects. No host imports, native workers or model/queue mutation.
        import json
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                      and n.name == "Native")
        methods = [n for n in native.body if isinstance(n, ast.FunctionDef)
                   and n.name == "_durable_submit_fence"]
        self.assertEqual(len(methods), 1)
        scope = {
            "document": lambda path, limit: json.loads(Path(path).read_text()),
            "GateError": RuntimeError, "time": time,
        }
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=methods, type_ignores=[])), str(SOURCE), "exec"), scope)
        self.assertEqual(SOURCE.read_text().count("self._durable_submit_fence(task)"), 2)
        for handler in ("owner_native_subagent_review", "owner_native_typed_leaf"):
            with self.subTest(handler=handler), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "state.json"
                task = {"id": "B1-RESTART-INTENT", "handler": handler,
                        "status": "running",
                        "owner_claim": {"nonce": "1234567890ab1234567890ab", "pid": 123},
                        "params": {"job_id": "stable-job"}}
                original = {"tasks": {task["id"]: dict(task)}}
                path.write_text(json.dumps(original))
                def saved(state):
                    path.write_text(json.dumps(state))
                first = SimpleNamespace(
                    state=original, source="exact-source", _pool_recovery_uncertain=False,
                    ns={"_qlock": threading.RLock(), "STATE": path, "save_state": saved})
                result = scope["_durable_submit_fence"](first, task)
                self.assertEqual(result["task_id"], task["id"])
                self.assertEqual(result["owner_claim"], task["owner_claim"])
                self.assertEqual(json.loads(path.read_text())["tasks"][task["id"]]
                                 ["native_worker_submit_intent"], result)
                # Crash/disconnect before worker reply. Reinitialize from saved
                # state with an empty in-memory interrupted/completed map.
                second_state = json.loads(path.read_text())
                restarted = SimpleNamespace(
                    state=second_state, source="exact-source",
                    interrupted={}, completed={}, _pool_recovery_uncertain=False,
                    ns={"_qlock": threading.RLock(), "STATE": path, "save_state": saved})
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_NATIVE_SUBMIT_INTENT_UNSETTLED"):
                    scope["_durable_submit_fence"](restarted, second_state["tasks"][task["id"]])
                self.assertEqual(second_state["tasks"][task["id"]]
                                 ["native_worker_submit_intent"], result)

    def test_durable_presubmit_unknown_readback_never_allows_ipc(self):
        import json
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                      and n.name == "Native")
        method = next(n for n in native.body if isinstance(n, ast.FunctionDef)
                      and n.name == "_durable_submit_fence")
        scope = {"document": lambda path, limit: json.loads(Path(path).read_text()),
                 "GateError": RuntimeError, "time": time}
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec"), scope)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            task = {"id": "B1-UNKNOWN-DURABLE", "handler": "owner_native_typed_leaf",
                    "status": "running", "owner_claim": {"nonce": "1234567890ab1234567890ab"},
                    "params": {"job_id": "job"}}
            state = {"tasks": {task["id"]: dict(task)}}
            path.write_text(json.dumps(state))
            # Simulate an ambiguous persistence layer: writer reports an error.
            def uncertain(_):
                raise OSError("unknown fsync outcome")
            owner = SimpleNamespace(state=state, source="source",
                _pool_recovery_uncertain=False,
                ns={"_qlock": threading.RLock(), "STATE": path, "save_state": uncertain})
            with self.assertRaisesRegex(RuntimeError,
                                        "HOLD_NATIVE_SUBMIT_INTENT_READBACK"):
                scope["_durable_submit_fence"](owner, task)
            self.assertTrue(owner._pool_recovery_uncertain)

    def test_durable_terminal_exact_receipt_s03_readback_after_restart(self):
        # AST-extracted methods, real queue JSON, no worker or live S03 POST.
        import hashlib
        import json
        import sqlite3
        import threading
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                      and n.name == "Native")
        names = {"_durable_terminal_fence", "_durable_terminal_s03_readback"}
        methods = [n for n in native.body if isinstance(n, ast.FunctionDef)
                   and n.name in names]
        self.assertEqual({n.name for n in methods}, names)
        def encoded(value):
            return json.dumps(value, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False).encode()
        def digest(value):
            return hashlib.sha256(value).hexdigest()
        committed = {"value": False}
        canonical_db = Path("/isolated/B1-durable-S03.sqlite")
        def canonical_proof(candidate):
            return {"native_verified": True,
                    "task_id": candidate["task_id"],
                    "job_id": candidate["job_id"],
                    "phase": candidate["phase"],
                    "receipt_sha256": digest(encoded(candidate)),
                    "s03_item_id": 9, "database": str(canonical_db)}
        scope = {
            "document": lambda path, limit: json.loads(Path(path).read_text()),
            "encoded": encoded, "digest": digest, "GateError": RuntimeError,
            "sqlite3": sqlite3, "DB": canonical_db,
            "HANDLER": "owner_native_subagent_review",
            "LEAF_HANDLER": "owner_native_typed_leaf",
            "RECEIPT": "NOX_NATIVE_SUBAGENT_RECEIPT_V1",
            "s03_readback": lambda receipt:
                canonical_proof(receipt) if committed["value"] else None,
        }
        exec(compile(ast.fix_missing_locations(
            ast.Module(body=methods, type_ignores=[])), str(SOURCE), "exec"), scope)
        self.assertEqual(SOURCE.read_text().count("self._durable_terminal_fence(task, result)"), 2)
        cases = (("owner_native_subagent_review",
                  "NATIVE_REVIEW_COMPLETED_CANDIDATE_NOT_APPLIED"),
                 ("owner_native_typed_leaf",
                  "NATIVE_LEAF_COMPLETED_ORIGINAL_NOT_ACCEPTED"))
        for handler, phase in cases:
            with self.subTest(handler=handler), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "state.json"
                claim = {"nonce": "1234567890ab1234567890ab", "pid": 41}
                task = {"id": "B1-TERMINAL-EXACT", "status": "running",
                        "handler": handler, "owner_claim": claim,
                        "params": {"job_id": "job1"}}
                if handler == "owner_native_typed_leaf":
                    task.update(parent_task_id="6V14-03", queue_id="queue-1")
                intent = {"schema": "NOX_NATIVE_WORKER_SUBMIT_INTENT_V1",
                          "task_id": task["id"], "handler": handler,
                          "owner_claim": claim, "job_id": "job1",
                          "source_sha256": "pinned-source", "created_at": 1.0}
                task["native_worker_submit_intent"] = intent
                receipt = {"schema": "NOX_NATIVE_SUBAGENT_RECEIPT_V1",
                           "phase": phase, "task_id": task["id"],
                           "job_id": "job1", "claim": claim,
                           "source_sha256": "pinned-source",
                           "worker_result": {"text": "Привет 🌍", "tokens": [1, 2, 3]}}
                if handler == "owner_native_typed_leaf":
                    receipt.update(parent_task_id="6V14-03", queue_id="queue-1",
                                   scope="SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED",
                                   original_task_accepted=False)
                state = {"tasks": {task["id"]: task}}
                path.write_text(json.dumps(state, ensure_ascii=False))
                def save(value):
                    path.write_text(json.dumps(value, ensure_ascii=False))
                owner = SimpleNamespace(
                    ns={"_qlock": threading.RLock(), "STATE": path,
                        "save_state": save},
                    state=state, source="pinned-source",
                    _pool_recovery_uncertain=False)
                evidence = scope["_durable_terminal_fence"](owner, task, receipt)
                self.assertEqual(evidence["receipt"], receipt)
                self.assertEqual(evidence["receipt_sha256"], digest(encoded(receipt)))
                committed["value"] = False
                self.assertIsNone(scope["_durable_terminal_s03_readback"](owner, task["id"]))
                committed["value"] = True
                restarted = SimpleNamespace(ns=owner.ns)
                restored = scope["_durable_terminal_s03_readback"](restarted, task["id"])
                self.assertEqual(restored["receipt"], receipt)
                self.assertEqual(restored["s03"]["receipt_sha256"],
                                 evidence["receipt_sha256"])
                # A digest-only or wrong-scope result cannot become a terminal
                # acceptance after STOP/reconnect. Verify exact source behavior
                # against missing/falsy metadata and cross-job/DB substitutions.
                trusted_reader = scope["s03_readback"]
                try:
                    scope["s03_readback"] = lambda _: {
                        "receipt_sha256": evidence["receipt_sha256"]}
                    self.assertIsNone(scope["_durable_terminal_s03_readback"](
                        restarted, task["id"]), "digest-only proof")
                    for field, wrong in (
                            ("native_verified", False),
                            ("native_verified", 1),
                            ("task_id", "foreign-task"),
                            ("job_id", "foreign-job"),
                            ("phase", "foreign-phase"),
                            ("s03_item_id", 0),
                            ("s03_item_id", True),
                            ("s03_item_id", "9"),
                            ("database", "/foreign/S03.sqlite"),
                            ("receipt_sha256", "0" * 64)):
                        with self.subTest(handler=handler, invalid_field=field,
                                          invalid_value=wrong):
                            bad = {**canonical_proof(receipt), field: wrong}
                            scope["s03_readback"] = lambda _, value=bad: value
                            self.assertIsNone(
                                scope["_durable_terminal_s03_readback"](
                                    restarted, task["id"]))
                finally:
                    scope["s03_readback"] = trusted_reader
                # The owner claim can change while a canonical S03 read is in
                # flight. A valid S03 digest of the old receipt must not settle
                # the newly persisted queue row. No actual worker/S03 POST.
                original_reader = scope["s03_readback"]
                try:
                    scope["s03_readback"] = lambda _: "invalid S03 shape"
                    self.assertIsNone(scope["_durable_terminal_s03_readback"](
                        restarted, task["id"]))
                    def claim_change_during_s03(candidate):
                        changed = json.loads(path.read_text())
                        changed["tasks"][task["id"]]["owner_claim"]["pid"] = 98765
                        save(changed)
                        return canonical_proof(candidate)
                    scope["s03_readback"] = claim_change_during_s03
                    self.assertIsNone(scope["_durable_terminal_s03_readback"](
                        restarted, task["id"]))
                finally:
                    scope["s03_readback"] = original_reader
                    save(state)
                # Recompute the forged receipt digest and accept its fake S03
                # digest. Exact leaf queue/parent/scope must STILL reject it.
                if handler == "owner_native_typed_leaf":
                    for key, value in (("queue_id", "foreign-queue"),
                                       ("parent_task_id", "foreign-parent"),
                                       ("original_task_accepted", True),
                                       ("scope", "PARENT_ACCEPTED")):
                        forged = json.loads(path.read_text())
                        terminal = forged["tasks"][task["id"]]["native_worker_terminal_evidence"]
                        terminal["receipt"][key] = value
                        terminal["receipt_sha256"] = digest(encoded(terminal["receipt"]))
                        save(forged)
                        self.assertIsNone(scope["_durable_terminal_s03_readback"](
                            restarted, task["id"]), key)
                        save(state)
                original_reader = scope["s03_readback"]
                try:
                    def unavailable(_):
                        raise OSError("ambiguous S03 read")
                    scope["s03_readback"] = unavailable
                    self.assertIsNone(scope["_durable_terminal_s03_readback"](
                        restarted, task["id"]))
                finally:
                    scope["s03_readback"] = original_reader
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_NATIVE_TERMINAL_INTENT_UNSETTLED"):
                    scope["_durable_terminal_fence"](owner, task, receipt)
                tampered = json.loads(path.read_text())
                tampered["tasks"][task["id"]]["native_worker_terminal_evidence"][
                    "receipt_sha256"] = "0" * 64
                save(tampered)
                self.assertIsNone(scope["_durable_terminal_s03_readback"](restarted, task["id"]))

    def test_s03_readback_nonobject_metadata_fails_closed(self):
        # Execute the actual S03 receipt reader without a live host connection.
        # Valid JSON with a non-dict root must not crash interrupted recovery.
        import contextlib
        import hashlib
        import json
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        functions = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef)
                     and node.name == "s03_readback"]
        self.assertEqual(len(functions), 1)

        class LocalCursor:
            def __init__(self, marker):
                self.marker = marker
                self.meta = None
            def execute(self, _sql, _args):
                return self
            def fetchall(self):
                return [(9, self.marker, self.meta,
                         hashlib.sha256(("M2|" + self.marker).encode()).hexdigest())]

        marker = "NOX durable terminal receipt TEST"
        cursor = LocalCursor(marker)
        @contextlib.contextmanager
        def local_s03_connection():
            yield cursor

        def encoded(value):
            return json.dumps(value, sort_keys=True,
                              separators=(",", ":")).encode()
        scope = {
            "json": json,
            "DB": Path("/nonexistent/isolated/readback.sqlite"),
            "encoded": encoded,
            "digest": lambda data: hashlib.sha256(data).hexdigest(),
            "memory_text": lambda _: marker,
            "s03_connection": local_s03_connection,
        }
        exec(compile(ast.fix_missing_locations(ast.Module(
            body=functions, type_ignores=[])), str(SOURCE), "exec"), scope)
        reader = scope["s03_readback"]
        receipt = {"task_id": "B1", "job_id": "job", "phase": "terminal"}
        for payload in ([], None, "not a dict", 7, True, {},
                        {"receipt": {"task_id": "foreign"}}):
            with self.subTest(meta=repr(payload)):
                cursor.meta = json.dumps(payload)
                self.assertIsNone(reader(receipt))
        cursor.meta = "{invalid-json"
        self.assertIsNone(reader(receipt))
        cursor.meta = json.dumps({"receipt": receipt})
        proof = reader(receipt)
        self.assertTrue(proof["native_verified"])
        self.assertEqual(proof["task_id"], "B1")
        self.assertEqual(proof["job_id"], "job")

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
