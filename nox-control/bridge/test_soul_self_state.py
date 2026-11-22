"""3A04 source-only: bounded self-model journal read and truthful health reporting."""
import ast
import io
import json
from collections import deque
from pathlib import Path
import types
import unittest


def selected_functions():
    filename = Path(__file__).with_name("nox_soul.py")
    tree = ast.parse(filename.read_text(encoding="utf-8"), filename=str(filename))
    names = {"_tail", "awareness_line"}
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != names:
        raise AssertionError("missing production self-model helpers")
    ns = {"json": json, "deque": deque}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(filename), "exec"), ns)
    return ns


class SelfStateTests(unittest.TestCase):
    def test_tail_never_calls_unbounded_read(self):
        ns = selected_functions()
        text = "".join(json.dumps({"seq": i}) + "\n" for i in range(5000))

        class NoReadFile(io.StringIO):
            def read(self, *args, **kwargs):
                raise AssertionError("whole-journal read is forbidden")

        ns["open"] = lambda *a, **kw: NoReadFile(text)
        self.assertEqual([x["seq"] for x in ns["_tail"]("state.jsonl", 6)],
                         [4994, 4995, 4996, 4997, 4998, 4999])
        self.assertEqual(ns["_tail"]("state.jsonl", 0), [])
        self.assertEqual(ns["_tail"]("state.jsonl", 257), [])

    def test_failed_supervisor_is_unknown_not_zero_processes(self):
        ns = selected_functions()
        ns["_c"] = {"t": 0, "v": ""}
        ns["JOURNAL"] = "mock-journal"
        ns["_tail"] = lambda *a: [42]  # corrupt non-mapping JSON must not crash
        ns["time"] = types.SimpleNamespace(time=lambda: 100)
        ns["subprocess"] = types.SimpleNamespace(
            run=lambda *a, **kw: types.SimpleNamespace(
                returncode=1, stdout="fake-service RUNNING pid 99"))
        ns["shutil"] = types.SimpleNamespace(
            disk_usage=lambda *a: types.SimpleNamespace(used=50, total=100))

        class Health:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False

        ns["urllib"] = types.SimpleNamespace(
            request=types.SimpleNamespace(urlopen=lambda *a, **kw: Health()))
        line = ns["awareness_line"]()
        self.assertIn("процессы: нет данных", line)
        self.assertNotIn("процессов работает 1", line)
        self.assertIn("/health=200, генерация не проверена", line)
        self.assertNotIn("модель жива", line)


if __name__ == "__main__":
    unittest.main()
