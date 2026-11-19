"""Adapter tests for the isolated NOX mind v4.1 staging layer."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "staging", "nox_mind_v41"))
sys.path.insert(0, os.path.join(ROOT, "staging"))

from nox_mind_v41.graph_memory import GraphMemory
from nox_mind_v41.persona import Persona
from nox_mind_v41.warm_cache import ScopedFTS, WarmS03Cache
from nox_mind_v41_adapters.dispatcher_adapter import DispatcherPlanAdapter
from nox_mind_v41_adapters.identity_adapter import PersonaIdentityAdapter
from nox_mind_v41_adapters.protocols import (
    DispatcherPort,
    IdentityPort,
    InMemoryDispatcher,
    InMemoryIdentity,
    InMemoryS03,
    S03MemoryPort,
    StagingDisabled,
    StagingRefused,
)
from nox_mind_v41_adapters.s03_adapter import S03MindAdapter, open_staging_memory


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def _persona(pid, warmth=0.8):
    return Persona(pid, "NOX", {"тепло": warmth}, {"язык": "ru"}, ["не выдаёт себя за человека"])


def _healthy_snapshot():
    return {
        "stop_active": False,
        "onehost": {"healthy": True},
        "s03": {"readback_verified": True},
        "trainer": {"running": False, "ready_for_resume": False},
        "gpu": {"temperature_sensor_valid": True, "temperature_c": 40, "utilization_pct": 80},
        "disk": {"free_gib": 100, "checkpoint_reserve_gib": 10},
    }


def _calc(expr):
    left, right = expr.split("+", 1)
    return str(int(left) + int(right))


class TestS03Adapter(unittest.TestCase):
    def setUp(self):
        os.environ.pop("NOX_MIND_V41_STAGING", None)
        self.clock = Clock(1000.0)
        self.mem = open_staging_memory(clock=self.clock, monotonic=self.clock)
        self.fake = InMemoryS03()

    def test_default_off_and_explicit_false_beat_env(self):
        adapter = S03MindAdapter(self.mem.store, self.mem.cache, self.mem.graph, port=self.fake)
        self.assertFalse(adapter.enabled)
        with self.assertRaises(StagingDisabled):
            adapter.write("P", "кофе")
        with self.assertRaises(StagingDisabled):
            adapter.read("P", "кофе")
        self.assertEqual(self.mem.store.db.execute("SELECT COUNT(*) FROM fact").fetchone()[0], 0)
        self.assertEqual(self.mem.graph.db.execute("SELECT COUNT(*) FROM node").fetchone()[0], 0)
        self.assertEqual(self.fake.rows, [])
        os.environ["NOX_MIND_V41_STAGING"] = "1"
        try:
            forced_off = S03MindAdapter(self.mem.store, self.mem.cache, self.mem.graph, enabled=False)
            self.assertFalse(forced_off.enabled)
            with self.assertRaises(StagingDisabled):
                forced_off.write("P", "кофе")
        finally:
            os.environ.pop("NOX_MIND_V41_STAGING", None)
        self.assertEqual(self.mem.store.db.execute("SELECT COUNT(*) FROM fact").fetchone()[0], 0)

    def test_env_flag_turns_adapter_on(self):
        os.environ["NOX_MIND_V41_STAGING"] = "yes"
        try:
            adapter = S03MindAdapter(self.mem.store, self.mem.cache, self.mem.graph)
            self.assertTrue(adapter.enabled)
        finally:
            os.environ.pop("NOX_MIND_V41_STAGING", None)

    def test_write_read_maps_facts_cache_and_graph(self):
        adapter = S03MindAdapter(self.mem.store, self.mem.cache, self.mem.graph, enabled=True, port=self.fake)
        self.assertIsInstance(adapter, S03MemoryPort)
        first = adapter.write("P", "любит кофе", subject="owner", predicate="drink", obj="кофе")
        again = adapter.write("P", "любит кофе", subject="owner", predicate="drink", obj="кофе")
        self.assertEqual(again["fact_id"], first["fact_id"])
        self.assertTrue(again["idempotent"])
        self.assertEqual(len(self.fake.rows), 1)
        self.assertEqual(self.mem.graph.db.execute("SELECT COUNT(*) FROM node").fetchone()[0], 1)
        view = adapter.read("P", "кофе", subject="owner", predicate="drink")
        self.assertEqual([row["object"] for row in view["facts"]], ["кофе"])
        self.assertIn(first["fact_id"], {item["id"] for item in view["warm"]})
        self.assertEqual(view["graph"][0]["id"], first["node_id"])
        self.assertEqual(self.fake.read("P", "кофе")[0]["fact_id"], first["fact_id"])
        self.assertEqual(self.fake.read("Q", "кофе"), [])

    def test_supersession_and_persona_isolation(self):
        adapter = S03MindAdapter(self.mem.store, self.mem.cache, self.mem.graph, enabled=True)
        adapter.write("P1", "кофе утром", subject="owner", predicate="drink", obj="кофе")
        self.clock.t += 1
        second = adapter.write("P1", "чай вечером", subject="owner", predicate="drink", obj="чай")
        adapter.write("P2", "только чай", subject="owner", predicate="drink", obj="чай")
        current = self.mem.store.current("P1", "owner", "drink")
        history = self.mem.store.history("P1", "owner", "drink")
        self.assertEqual([row["object"] for row in current], ["чай"])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["expired_at"], 1001.0)
        view = adapter.read("P1", "чай", subject="owner", predicate="drink")
        self.assertEqual([row["id"] for row in view["facts"]], [second["fact_id"]])
        self.assertIn(second["fact_id"], {item["id"] for item in view["warm"]})
        self.assertIn("чай вечером", {item["text"] for item in view["warm"]})
        leaked = [item for item in view["warm"] if item["text"] == "только чай"]
        self.assertEqual(leaked, [])
        self.assertEqual(self.mem.store.current("P2", "owner", "drink")[0]["object"], "чай")
        self.assertTrue(all(node["text"] != "только чай" for node in self.mem.graph.recall("P1", "чай")))

    def test_refuses_host_s03_path(self):
        with self.assertRaises(StagingRefused):
            open_staging_memory("/workspace/nox/memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3")
        with self.assertRaises(StagingRefused):
            open_staging_memory(r"C:\memory\unified_nox_knowledge.sqlite3")
        opened = open_staging_memory()
        self.assertEqual(opened.store.db.execute("SELECT COUNT(*) FROM fact").fetchone()[0], 0)


class TestDispatcherAdapter(unittest.TestCase):
    def test_fakes_do_not_submit(self):
        fake = InMemoryDispatcher()
        self.assertIsInstance(fake, DispatcherPort)
        job = fake.submit_goal("проверить", "tool_agent", snapshot={"stop_active": True})
        self.assertFalse(job["submitted"])
        self.assertEqual(len(fake.jobs), 1)

    def test_disabled_plans_nothing(self):
        prompts = []
        adapter = DispatcherPlanAdapter(lambda prompt: prompts.append(prompt), {"calc": _calc}, enabled=False)
        with self.assertRaises(StagingDisabled):
            adapter.submit("цель")
        self.assertEqual(prompts, [])
        self.assertEqual(adapter.admissions, [])

    def test_plan_then_execute_uses_preset_and_checkpoint(self):
        prompts = []

        def llm(prompt):
            prompts.append(prompt)
            if prompt.startswith("Цель:"):
                return "calc(1+1)\nитог"
            return "готово"

        clock = Clock(50.0)
        graph = GraphMemory(clock=clock)
        adapter = DispatcherPlanAdapter(llm, {"calc": _calc}, enabled=True, graph=graph)
        self.assertIsInstance(adapter, DispatcherPort)
        out = adapter.submit_goal("посчитать", preset="tool_agent", snapshot=_healthy_snapshot(), task_id="task-1")
        self.assertEqual(out["status"], "STAGED")
        self.assertTrue(out["executed"])
        self.assertFalse(out["submitted_to_host"])
        self.assertEqual(out["request"]["temperature"], 0.1)
        self.assertEqual(out["request"]["reasoning_effort"], "50")
        self.assertEqual(out["results"][0]["out"], "2")
        self.assertEqual(out["results"][1]["out"], "готово")
        self.assertEqual(graph.resume("task-1")["step"], 1)
        self.assertEqual(len(prompts), 2)

    def test_hold_on_stop_and_unverified_s03(self):
        prompts = []
        adapter = DispatcherPlanAdapter(lambda prompt: prompts.append(prompt) or "x", {"calc": _calc}, enabled=True)
        stopped = adapter.submit("цель", snapshot={"stop_active": True})
        self.assertEqual(stopped["status"], "HOLD")
        self.assertFalse(stopped["executed"])
        self.assertEqual(stopped["reason"]["advice"][0]["code"], "STOP_ACTIVE")
        unverified = {
            "stop_active": False,
            "onehost": {"healthy": True},
            "s03": {"readback_verified": False},
            "trainer": {"running": False},
            "gpu": {"temperature_sensor_valid": True, "temperature_c": 40, "utilization_pct": 50},
            "disk": {"free_gib": 100, "checkpoint_reserve_gib": 10},
        }
        held = adapter.submit("цель", snapshot=unverified)
        self.assertEqual(held["status"], "HOLD")
        self.assertFalse(held["executed"])
        self.assertEqual(held["reason"]["advice"][0]["code"], "S03_NOT_VERIFIED")
        self.assertEqual(prompts, [])
        self.assertTrue(all(row["submitted_to_host"] is False for row in adapter.admissions))


class TestIdentityAdapter(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.fts = ScopedFTS()
        self.cache = WarmS03Cache(self.fts, ttl_s=100, clock=self.clock)

    def test_switch_invalidates_persona_not_core(self):
        self.cache.write("1", "P1", "persona", "кофе утром")
        self.cache.recall("кофе", "P1")
        self.cache.recall("кофе", "P1")
        self.assertEqual(self.cache.hits, 1)
        generation = self.cache._gen["P1"]
        misses = self.cache.misses
        port = InMemoryIdentity()
        adapter = PersonaIdentityAdapter(self.cache, enabled=True, identity_port=port)
        self.assertIsInstance(adapter, IdentityPort)
        first = _persona("P1")
        bound = adapter.bind("core-1", first, emotion_label="sadness")
        self.assertEqual(adapter.current_ids(), ("core-1", "P1"))
        self.assertEqual(port.current_ids(), ("core-1", "P1"))
        self.assertIn("P1", bound["system_block"])
        self.assertIn("sadness", bound["system_block"])
        self.assertEqual(self.cache._gen["P1"], generation)
        adapter.bind("core-2", first)
        self.assertEqual(adapter.current_ids(), ("core-2", "P1"))
        self.assertEqual(self.cache._gen["P1"], generation)
        self.cache.recall("кофе", "P1")
        self.assertEqual(self.cache.hits, 2)
        adapter.switch("core-2", _persona("P2", warmth=0.2))
        self.assertEqual(self.cache._gen["P1"], generation + 1)
        self.assertEqual(adapter.current_ids(), ("core-2", "P2"))
        self.assertEqual(port.current_ids()[1], "P2")
        self.cache.recall("кофе", "P1")
        self.assertEqual(self.cache.misses, misses + 1)
        self.assertIn("P2", adapter.system_block())

    def test_switch_persona_clears_card_and_disabled_is_inert(self):
        self.cache.write("1", "P1", "persona", "кофе утром")
        generation = self.cache._gen["P1"]
        adapter = PersonaIdentityAdapter(self.cache, enabled=True)
        adapter.bind("core-1", _persona("P1"))
        adapter.switch_persona("P9")
        self.assertEqual(adapter.current_ids(), ("core-1", "P9"))
        self.assertEqual(self.cache._gen["P1"], generation + 1)
        self.assertEqual(adapter.system_block(), "")
        self.assertIsNone(adapter.persona)
        off = PersonaIdentityAdapter(self.cache, enabled=False)
        before = dict(self.cache._gen)
        with self.assertRaises(StagingDisabled):
            off.bind("core-x", _persona("P1"))
        self.assertIsNone(off.binding)
        self.assertEqual(self.cache._gen, before)

    def test_in_memory_identity_fake(self):
        ident = InMemoryIdentity()
        self.assertIsInstance(ident, IdentityPort)
        self.assertEqual(ident.current_ids(), ("core-unset", "persona-unset"))
        ident.switch_persona("P9")
        self.assertEqual(ident.current_ids(), ("core-unset", "P9"))


if __name__ == "__main__":
    unittest.main()
