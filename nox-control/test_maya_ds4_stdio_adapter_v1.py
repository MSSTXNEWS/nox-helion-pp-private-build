import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "adapter", Path(__file__).with_name("maya_ds4_stdio_adapter_v1.py"))
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


class FakeIn:
    def __init__(self):
        self.writes = []
    def write(self, text):
        self.writes.append(text)
    def flush(self):
        pass


class FakeOut:
    def __init__(self, lines):
        self.lines = iter(lines)
    def readline(self):
        return next(self.lines, "")


class FakeProcess:
    def __init__(self, lines):
        self.stdin, self.stdout = FakeIn(), FakeOut(lines)
        self.waited = False
    def wait(self, timeout=None):
        self.waited = True
    def terminate(self):
        pass


class AdapterTests(unittest.TestCase):
    def test_disabled_is_hold_and_never_spawns(self):
        spawned = []
        adapter = ADAPTER.MayaStdioAdapter(["maya-ds4", "--serve"],
                                           popen=lambda *a, **k: spawned.append(a))
        self.assertEqual(adapter.state, "HOLD_MAYA_BINARY_EXECUTED_FALSE")
        with self.assertRaisesRegex(ADAPTER.MayaAdapterHold, "MAYA_BINARY_EXECUTED=false"):
            adapter.start()
        with self.assertRaises(ADAPTER.MayaAdapterHold):
            next(adapter.generate_ids([1], 4))
        self.assertEqual(spawned, [])

    def test_ready_gen_token_done_and_normal_completion_has_no_stop(self):
        proc = FakeProcess(["INFO engine=ds4\n", "READY 4096 stop\n",
                            "STAT x\n", "T 23\n", "T 24\n", "DONE 2 3 4.0 1.0 length 0 0 0 0 0\n"])
        calls = []
        adapter = ADAPTER.MayaStdioAdapter(["maya-ds4", "--serve"], enabled=True,
                                           popen=lambda *a, **k: calls.append((a, k)) or proc)
        self.assertEqual(list(adapter.generate_ids([1, 2, 3], 8)), [23, 24])
        self.assertIn("GEN 8 1,2,3\n", proc.stdin.writes)
        self.assertNotIn("STOP\n", proc.stdin.writes)
        self.assertFalse(adapter.gpu_stop_verified)
        self.assertEqual(adapter.state, "PROCESS_READY")
        adapter.close()
        self.assertIn("QUIT\n", proc.stdin.writes)
        self.assertTrue(proc.waited)

    def test_consumer_cancel_sends_stop_then_drains_done(self):
        proc = FakeProcess(["READY 4096 stop\n", "T 99\n",
                            "DONE 1 3 4.0 1.0 cancel 0 0 0 0 0\n"])
        adapter = ADAPTER.MayaStdioAdapter(["maya-ds4", "--serve"], enabled=True,
                                           popen=lambda *a, **k: proc)
        stream = adapter.generate_ids([7, 8], 4)
        self.assertEqual(next(stream), 99)
        stream.close()
        self.assertEqual(proc.stdin.writes[-1], "STOP\n")
        self.assertFalse(adapter.gpu_stop_verified)

    def test_ready_without_stop_fails_closed(self):
        proc = FakeProcess(["READY 4096\n"])
        adapter = ADAPTER.MayaStdioAdapter(["maya-ds4", "--serve"], enabled=True,
                                           popen=lambda *a, **k: proc)
        with self.assertRaisesRegex(ADAPTER.MayaAdapterHold, "STOP_UNSUPPORTED"):
            list(adapter.generate_ids([1], 4))


if __name__ == "__main__":
    unittest.main()
