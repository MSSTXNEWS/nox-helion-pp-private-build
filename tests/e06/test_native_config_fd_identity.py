"""Original E06 config: stable FD, reparse/TOCTOU denial, bounded exact-byte parse."""
import ast
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

OWNER = Path(__file__).resolve().parents[2] / "coordination/e06/e06_native_stdio_owner.py"


def original_reader():
    parsed = ast.parse(OWNER.read_text("utf-8"))
    funcs = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
             and node.name in {"_plain_path", "_read_native_config_bytes"}]
    if len(funcs) != 2:
        raise AssertionError("Original E06 config functions missing")
    scope = {"Path": Path, "stat": stat, "os": os}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(OWNER), "exec"), scope)
    return scope["_read_native_config_bytes"]


class NativeConfigDescriptorIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "onehost-native-config.json"
        self.reader = original_reader()

    def test_original_valid_bytes(self):
        raw = b'{"version": 1}'
        self.config.write_bytes(raw)
        self.assertEqual(self.reader(self.root, self.config), raw)

    def test_oversized_before_parse(self):
        self.config.write_bytes(b"0" * 65537)
        with self.assertRaisesRegex(ValueError, "E06_NATIVE_CONFIG_FORMAT_HOLD"):
            self.reader(self.root, self.config)

    def test_symlink_is_denied(self):
        outside = self.root / "other.json"
        outside.write_bytes(b'{"version": 2}')
        try:
            self.config.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on test host")
        with self.assertRaises(ValueError):
            self.reader(self.root, self.config)

    def test_swap_during_open_is_denied(self):
        self.config.write_bytes(b'{"version": 1}')
        original = os.open
        calls = []
        def swap(path, flags, *args, **kwargs):
            calls.append(1)
            self.config.unlink()
            self.config.write_bytes(b'{"version": 999}')
            return original(path, flags, *args, **kwargs)
        with mock.patch.object(os, "open", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "E06_NATIVE_CONFIG_IDENTITY_HOLD"):
                self.reader(self.root, self.config)
        self.assertEqual(len(calls), 1)

    def test_swap_after_read_is_denied(self):
        self.config.write_bytes(b'{"version": 1}')
        original = os.read
        def swap(fd, size):
            data = original(fd, size)
            self.config.unlink()
            self.config.write_bytes(b'{"version": 999}')
            return data
        with mock.patch.object(os, "read", side_effect=swap):
            with self.assertRaisesRegex(ValueError, "E06_NATIVE_CONFIG_IDENTITY_HOLD"):
                self.reader(self.root, self.config)

    def test_in_place_mutation_after_read_is_denied(self):
        self.config.write_bytes(b'{"version": 1}')
        original = os.read
        def mutate(fd, size):
            raw = original(fd, size)
            with self.config.open("ab") as file:
                file.write(b" changed")
            return raw
        with mock.patch.object(os, "read", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "E06_NATIVE_CONFIG_IDENTITY_HOLD"):
                self.reader(self.root, self.config)

    def test_short_read_cannot_parse_valid_prefix(self):
        self.config.write_bytes(b'{"version": 1} EXTRA')
        original = os.read
        def shorten(fd, size):
            return original(fd, 14)
        with mock.patch.object(os, "read", side_effect=shorten):
            with self.assertRaisesRegex(ValueError, "E06_NATIVE_CONFIG_IDENTITY_HOLD"):
                self.reader(self.root, self.config)


if __name__ == "__main__":
    unittest.main()
