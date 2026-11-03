"""Source admission and frozen-container coverage are not Windows/E07 acceptance."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("coverage_gate", ROOT / "coordination/e06/t06_frozen_source_coverage.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class FrozenCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = []
        self.add("nox_selfbuilder/__init__.py", b"# package\n")
        self.add("nox_selfbuilder/ready.py", b"VALUE = 1\n")
        self.add("helion/e06_native_stdio_owner.py", b"VALUE = 2\n")
        self.add("Packages/P04/train_qlora.py", b"# separate approved interpreter\n")
    def add(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        self.rows.append(("src/" + name, name, MOD._blob(raw)))
    def test_all_admitted_modules_not_second_manual_list(self):
        self.add("nox_selfbuilder/new_ready.py", b"VALUE = 3\n")
        plan = MOD.module_plan(self.root, self.rows)
        self.assertEqual([r["module"] for r in plan], ["helion.e06_native_stdio_owner", "nox_selfbuilder", "nox_selfbuilder.new_ready", "nox_selfbuilder.ready"])
        self.assertFalse(any("train_qlora" in r["module"] for r in plan))
    def test_changed_source_and_invalid_pin_rejected(self):
        (self.root / "nox_selfbuilder/ready.py").write_bytes(b"VALUE = 9\n")
        with self.assertRaisesRegex(RuntimeError, "SOURCE_PIN_HOLD"):
            MOD.module_plan(self.root, self.rows)
        with self.assertRaisesRegex(RuntimeError, "PIN_HOLD"):
            MOD.module_plan(self.root, [("src/a.py", "a.py", "x" * 40)])
    def test_crlf_matches_only_canonical_pin(self):
        path = self.root / "nox_selfbuilder/ready.py"
        path.write_bytes(b"VALUE = 1\r\n")
        self.assertEqual(len(MOD.module_plan(self.root, self.rows)), 3)
        path.write_bytes(b"VALUE = 1\r")
        with self.assertRaisesRegex(RuntimeError, "SOURCE_PIN_HOLD"):
            MOD.module_plan(self.root, self.rows)
    def test_duplicate_destination_and_module_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "DESTINATION_COLLISION"):
            MOD.module_plan(self.root, self.rows + [self.rows[0]])
        self.add("nox_selfbuilder.py", b"# collision\n")
        with self.assertRaisesRegex(RuntimeError, "MODULE_COLLISION"):
            MOD.module_plan(self.root, self.rows)
    def test_traversal_and_noncanonical_paths_rejected(self):
        for name in ("../a.py", "/a.py", "a//b.py", "a/./b.py", "C:/a.py", "a\\b.py", "a\x00.py"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                MOD.module_plan(self.root, [("src/a.py", name, "0" * 40)])
    def test_symlink_rejected(self):
        path = self.root / "nox_selfbuilder/ready.py"
        path.unlink()
        try:
            path.symlink_to(self.root / "helion/e06_native_stdio_owner.py")
        except OSError:
            self.skipTest("Host does not permit test symlinks")
        with self.assertRaisesRegex(RuntimeError, "REPARSE_HOLD"):
            MOD.module_plan(self.root, self.rows)
    def test_invalid_python_and_module_name_rejected(self):
        self.add("broken.py", b"def :\n")
        with self.assertRaises(SyntaxError):
            MOD.module_plan(self.root, self.rows)
        self.rows.pop()
        self.add("bad-name.py", b"VALUE = 1\n")
        with self.assertRaisesRegex(RuntimeError, "MODULE_HOLD"):
            MOD.module_plan(self.root, self.rows)
    def reader(self, modules, raw=b"{\"v\":1}"):
        class Reader:
            toc = {"PYZ.pyz": (0, 10, 10, 0, "z"), "nox_selfbuilder/catalog.json": (0, len(raw), len(raw), 0, "x")}
            def open_embedded_archive(self, name):
                return type("PYZ", (), {"toc": {name: (0, 0, 0) for name in modules}})()
            def extract(self, name):
                return raw
        return Reader()
    def fixture(self):
        plan = MOD.module_plan(self.root, self.rows)
        data = [{"runtime_path": "nox_selfbuilder/catalog.json", "sha256": hashlib.sha256(b"{\"v\":1}").hexdigest()}]
        return plan, data, self.reader([r["module"] for r in plan])
    def test_frozen_missing_module_rejected(self):
        plan, data, reader = self.fixture()
        with self.assertRaisesRegex(RuntimeError, "FROZEN_MODULES_MISSING"):
            MOD.verify_archive_contents(self.reader([]), plan, data)
    def test_frozen_missing_or_changed_data_rejected(self):
        plan, data, reader = self.fixture()
        del reader.toc["nox_selfbuilder/catalog.json"]
        with self.assertRaisesRegex(RuntimeError, "FROZEN_DATA_MISSING"):
            MOD.verify_archive_contents(reader, plan, data)
        with self.assertRaisesRegex(RuntimeError, "FROZEN_DATA_SHA_HOLD"):
            MOD.verify_archive_contents(self.reader([r["module"] for r in plan], b"changed"), plan, data)
    def test_frozen_duplicate_data_and_name_rejected(self):
        plan, data, reader = self.fixture()
        with self.assertRaisesRegex(RuntimeError, "DATA_DUPLICATE"):
            MOD.verify_archive_contents(reader, plan, data + data)
        reader.toc["NOX_SELFBUILDER/CATALOG.JSON"] = reader.toc["nox_selfbuilder/catalog.json"]
        with self.assertRaisesRegex(RuntimeError, "ARCHIVE_NAME_COLLISION"):
            MOD.verify_archive_contents(reader, plan, data)
    def test_success_is_coverage_not_release_acceptance(self):
        plan, data, reader = self.fixture()
        proof = MOD.verify_archive_contents(reader, plan, data)
        self.assertEqual(proof["modules_checked"], 3)
        self.assertEqual(proof["data_files_checked"], 1)
        self.assertIs(proof["release_accepted"], False)
        self.assertEqual(proof["independent_e07"], "NOT_RUN")

if __name__ == "__main__":
    unittest.main()
