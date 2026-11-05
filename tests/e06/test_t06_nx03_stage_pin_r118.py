"""R118: NX03 binding and dependencies have exact immutable Git source pins."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nox_r118_stage_native_stdio", ROOT / "coordination/e06/stage_native_stdio.py")
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)
REQUIRED = (
    "src/nox_selfbuilder/onehost_builder.py",
    "src/nox_selfbuilder/nx03_model_firstcycle.py",
    "src/nox_selfbuilder/firstcycle_native.py",
    "src/nox_selfbuilder/selfwrite_native_gate.py",
)


class R118NX03Pins(unittest.TestCase):
    def test_new_native_modules_use_current_exact_blobs(self):
        pins = {src: (dest, pin) for src, dest, pin in STAGE.ADDONS}
        self.assertEqual(len(pins), len(STAGE.ADDONS))
        for path in REQUIRED:
            self.assertIn(path, pins)
            dest, pin = pins[path]
            self.assertEqual(dest, path.replace("src/", "", 1))
            raw = (ROOT / path).read_bytes()
            self.assertEqual(
                hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                pin)
            self.assertEqual(STAGE.pinned_bytes(ROOT / path, pin), raw)
    def test_unknown_pin_must_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "E06_NATIVE_OWNER_BLOB_SHA_HOLD"):
            STAGE.pinned_bytes(ROOT / REQUIRED[0], "0" * 40)


if __name__ == "__main__":
    unittest.main()
