"""Focused source regression for 1A03 process-local browser reconnect snapshots.

No model, S03, server, credentials or network required. Exercise the exact
production helper function AST with isolated state.
"""
import ast
import pathlib
import time
import unittest


def helpers():
    path = pathlib.Path(__file__).with_name("nox_webapi.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    names = {"_prune_chat_snapshots", "_reserve_chat_snapshot_slot"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in names]
    if len(nodes) != len(names):
        raise AssertionError("missing production stream snapshot helpers")
    ns = {"time": time, "CHAT_SNAPSHOTS": {}, "ACTIVE_CHAT_IDS": set(),
          "MAX_CHAT_SNAPSHOTS": 24, "CHAT_SNAPSHOT_TTL_S": 120}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return ns


def row(request_id, age=1):
    return {"request_id": request_id, "updated_at": time.monotonic() - age}


class ActiveSnapshotCapacityTest(unittest.TestCase):
    def test_expired_active_survives_privacy_prune(self):
        ns = helpers()
        ns["ACTIVE_CHAT_IDS"].add("inflight")
        ns["CHAT_SNAPSHOTS"].update({
            "live": row("inflight", 121),
            "finished": row("completed", 121),
        })
        ns["_prune_chat_snapshots"]()
        self.assertEqual(list(ns["CHAT_SNAPSHOTS"]), ["live"])

    def test_all_active_capacity_fails_without_eviction(self):
        ns = helpers()
        for n in range(24):
            key = f"req-{n}"
            ns["ACTIVE_CHAT_IDS"].add(key)
            ns["CHAT_SNAPSHOTS"][key] = row(key, 121)
        before = dict(ns["CHAT_SNAPSHOTS"])
        self.assertFalse(ns["_reserve_chat_snapshot_slot"]())
        self.assertEqual(ns["CHAT_SNAPSHOTS"], before)

    def test_old_idle_slot_reused_without_evicting_active(self):
        ns = helpers()
        for n in range(23):
            key = f"req-{n}"
            ns["ACTIVE_CHAT_IDS"].add(key)
            ns["CHAT_SNAPSHOTS"][key] = row(key, 1)
        ns["CHAT_SNAPSHOTS"]["old-idle"] = row("completed", 1)
        self.assertTrue(ns["_reserve_chat_snapshot_slot"]())
        self.assertEqual(len(ns["CHAT_SNAPSHOTS"]), 23)
        self.assertNotIn("old-idle", ns["CHAT_SNAPSHOTS"])
        self.assertTrue(all(key in ns["CHAT_SNAPSHOTS"] for key in ns["ACTIVE_CHAT_IDS"]))

    def test_ephemeral_free_slot_after_ttl_prune(self):
        ns = helpers()
        ns["CHAT_SNAPSHOTS"]["expired"] = row("completed", 121)
        self.assertTrue(ns["_reserve_chat_snapshot_slot"]())
        self.assertEqual(ns["CHAT_SNAPSHOTS"], {})


if __name__ == "__main__":
    unittest.main()
