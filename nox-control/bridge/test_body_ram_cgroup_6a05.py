"""RELAY35 6A05: self-state RAM claims must match the container, never imply admission."""
import ast
import io
from pathlib import Path
import unittest


def load_ram_status(files):
    source = Path(__file__).with_name("nox_bridge.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == "_ram_status")
    def file_open(path, encoding=None):
        if path not in files:
            raise FileNotFoundError(path)
        value = files[path]
        if isinstance(value, Exception):
            raise value
        return io.StringIO(value)
    ns = {"open": file_open}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), ns)
    return ns["_ram_status"]


class RamTruth6A05(unittest.TestCase):
    def test_finite_v2_cgroup_outweighs_large_host(self):
        ram = load_ram_status({
            "/sys/fs/cgroup/memory.max": str(194065203200),
            "/sys/fs/cgroup/memory.current": str(193053593600),
            "/proc/meminfo": "MemAvailable: 200000000 kB\n",
        })()
        self.assertIn("RAM cgroup: остаток лимита 0.94 ГиБ", ram)
        self.assertIn("не допуск", ram)
        self.assertNotIn("RAM хоста", ram)

    def test_broken_finite_limit_fails_closed_instead_of_host_fallback(self):
        for limit, used in (("194065203200", "not-a-number"),
                            ("194065203200", "194065203201"),
                            ("garbled", "0"),
                            ("-1", "0")):
            with self.subTest(limit=limit, used=used):
                ram = load_ram_status({
                    "/sys/fs/cgroup/memory.max": limit,
                    "/sys/fs/cgroup/memory.current": used,
                    "/proc/meminfo": "MemAvailable: 200000000 kB\n",
                })()
                self.assertEqual(ram, "RAM cgroup: нет данных")

    def test_v1_finite_limit_supported(self):
        ram = load_ram_status({
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": "4294967296",
            "/sys/fs/cgroup/memory/memory.usage_in_bytes": "3221225472",
            "/proc/meminfo": "MemAvailable: 200000000 kB\n",
        })()
        self.assertIn("RAM cgroup: остаток лимита 1.00 ГиБ", ram)

    def test_unlimited_cgroup_identifies_host_metric_as_host_only(self):
        ram = load_ram_status({
            "/sys/fs/cgroup/memory.max": "max",
            "/proc/meminfo": "MemAvailable: 1048576 kB\n",
        })()
        self.assertIn("RAM хоста: MemAvailable 1.00 ГиБ", ram)
        self.assertIn("cgroup без лимита", ram)


if __name__ == "__main__":
    unittest.main()
