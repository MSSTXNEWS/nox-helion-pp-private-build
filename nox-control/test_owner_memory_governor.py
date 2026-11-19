"""Focused native memory-governor invariants. No real reclaim or host I/O."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

FILE = Path(__file__).parent / "owner_memory_governor.py"
spec = importlib.util.spec_from_file_location("nox_owner_memory_governor", FILE)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
G = 1024 ** 3


def fixture(root, *, current=193*G, limit=194*G,
            file=188*G, shmem=75*G, inactive=105*G, anon=4*G,
            some=0, full=0, oom=0, high=0, kill=0):
    files = {
      "memory.current": str(current),
      "memory.max": str(limit),
      "memory.stat": (f"anon {anon}\nfile {file}\nshmem {shmem}\n"
                      f"inactive_file {inactive}\n"),
      "memory.events": (f"low 0\nhigh {high}\nmax 0\noom {oom}\n"
                        f"oom_kill {kill}\n"),
      "memory.pressure": (
          f"some avg10={some:.2f} avg60=0.00 avg300=0.00 total=42\n"
          f"full avg10={full:.2f} avg60=0.00 avg300=0.00 total=0\n"),
      "cpu.pressure": ("some avg10=0.00 avg60=0.00 avg300=0.00 total=1\n"
                       "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"),
      "memory.swap.current": "0",
      "memory.swap.max": "0",
      "memory.zswap.current": "0",
    }
    for key, value in files.items():
        (root / key).write_text(value)


class GovernorTests(unittest.TestCase):
    def test_cache_not_an_oom(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root)
            snapshot=g.sample(root)
            result=g.decide(snapshot)
            self.assertEqual(snapshot["reclaimable_file_estimate_bytes"],105*G)
            self.assertEqual(snapshot["effective_bytes_estimate"],88*G)
            self.assertEqual(result["state"],"CACHE_HEALTHY")
            self.assertEqual(result["cache_action"],"PRESERVE_PAGE_CACHE")
            self.assertFalse(result["automated_reclaim_executed"])

    def test_shmem_never_reclaimable_file_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root,file=175*G,shmem=150*G,inactive=100*G)
            sample=g.sample(root)
            self.assertEqual(sample["reclaimable_file_estimate_bytes"],25*G)
            self.assertEqual(g.decide(sample)["shmem_protected_bytes"],150*G)

    def test_memory_pressure_holds_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root,some=12.0,full=2.5)
            state=g.decide(g.sample(root))
            self.assertEqual(state["state"],"PRESSURE_CRITICAL")
            self.assertEqual(state["background_action"],"HOLD_NEW_BACKGROUND_SUBMITS")
            self.assertEqual(state["cache_action"],"REVIEW_COLD_FILE_FADVISE_CANDIDATES")
            self.assertFalse(state["model_shmem_deleted"])

    def test_elevated_pressure_reduces_not_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root,some=3.0)
            state=g.decide(g.sample(root))
            self.assertEqual(state["state"],"PRESSURE_ELEVATED")
            self.assertEqual(state["background_action"],"REDUCE_BACKGROUND_CONCURRENCY")

    def test_oom_delta_requires_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root,oom=8,kill=5)
            prev=g.sample(root)
            fixture(root,oom=9,kill=6)
            state=g.decide(g.sample(root),previous=prev)
            self.assertEqual(state["state"],"PRESSURE_CRITICAL")
            self.assertEqual(state["oom_kill_delta"],1)

    def test_initial_oom_total_does_not_prove_recent_oom(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root,oom=999,kill=55)
            state=g.decide(g.sample(root))
            self.assertIsNone(state["oom_kill_delta"])
            self.assertEqual(state["state"],"CACHE_HEALTHY")

    def test_owner_stop_yield_and_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root)
            snap=g.sample(root)
            self.assertEqual(g.decide(snap,chat_active=True)["background_action"],
                             "YIELD_TO_FOREGROUND_CHAT")
            self.assertEqual(g.decide(snap,writer_busy=True)["background_action"],
                             "HOLD_OWNER_MAINTENANCE")

    def test_symlink_cgroup_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root)
            (root/"memory.current").unlink()
            (root/"memory.current").symlink_to(root/"memory.max")
            with self.assertRaisesRegex(g.MemoryHold,"HOLD_MEMORY_GOVERNOR_CGROUP_SYMLINK"):
                g.sample(root)

    def test_duplicate_stat_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root)
            with (root/"memory.stat").open("a") as f:f.write("file 10\n")
            with self.assertRaisesRegex(g.MemoryHold,"DUPLICATE_OR_MALFORMED_STAT"):
                g.sample(root)

    def test_infinite_psi_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root)
            (root/"memory.pressure").write_text(
                "some avg10=NaN avg60=0.00 avg300=0.00 total=0\n"
                "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
            with self.assertRaises(g.MemoryHold):
                g.sample(root)

    def test_unlimited_cgroup_is_not_ratio_fabrication(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root)
            (root/"memory.max").write_text("max")
            result=g.decide(g.sample(root))
            self.assertIsNone(result["raw_ratio"])
            self.assertIsNone(result["effective_ratio_estimate"])

    def test_counter_reset_is_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            fixture(root,kill=2)
            prev=g.sample(root)
            fixture(root,kill=0)
            with self.assertRaisesRegex(g.MemoryHold,"EVENT_COUNTER_RESET"):
                g.decide(g.sample(root),previous=prev)


if __name__ == "__main__":
    unittest.main()
