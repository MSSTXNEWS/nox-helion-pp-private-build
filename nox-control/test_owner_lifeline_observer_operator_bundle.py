import base64
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import owner_native_operator as operator


ROOT = Path(__file__).resolve().parent
EXPECTED_ASSET_NAMES = (
    "nox_lifeline_observer.py",
    "lifeline-observer.json",
    "nox-lifeline-observer.service",
    "nox_lifeline_observer_bootstrap.py",
    "nox-lifeline-observer.conf",
)
SYSTEMD_ASSET_NAMES = EXPECTED_ASSET_NAMES[:3]


def load_installer():
    path = ROOT / "owner_native_lifeline_observer.py"
    spec = importlib.util.spec_from_file_location("lifeline_observer_installer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LifelineObserverOperatorBundleTests(unittest.TestCase):
    def test_existing_lifeline_action_routes_observer_installer(self):
        self.assertEqual(operator.FILES["lifeline"],
                         "nox-control/owner_native_lifeline_observer.py")
        installer = load_installer()
        self.assertEqual(tuple(installer.MAX_BYTES), SYSTEMD_ASSET_NAMES)
        self.assertEqual(set(installer.FILES), set(SYSTEMD_ASSET_NAMES))
        self.assertEqual(installer.SCRIPT.name, "nox_lifeline_observer.py")
        self.assertEqual(installer.BUNDLE_SHA256,
                         {name: pin for name, _, pin, _ in
                          operator.LIFELINE_OBSERVER_ASSET_PINS
                          if name in SYSTEMD_ASSET_NAMES})
        self.assertEqual(installer.SUPERVISOR_BUNDLE_SHA256,
                         {name: pin for name, _, pin, _ in
                          operator.LIFELINE_OBSERVER_ASSET_PINS
                          if name not in SYSTEMD_ASSET_NAMES})
        self.assertNotIn("nox_lifeline_observer_bootstrap.py", installer.FILES)
        self.assertNotIn("nox-lifeline-observer.conf", installer.FILES)

    def test_bundle_has_only_exact_pinned_observer_artifacts(self):
        assets = operator.build_lifeline_observer_bundle()
        self.assertEqual(tuple(assets), EXPECTED_ASSET_NAMES)
        self.assertNotIn("nox_native_lifeline.py", assets)
        self.assertNotIn("lifeline.example.json", assets)
        self.assertNotIn("nox-lifeline-guard.conf", assets)
        for name, _, pinned_sha256, _ in operator.LIFELINE_OBSERVER_ASSET_PINS:
            with self.subTest(asset=name):
                raw = base64.b64decode(assets[name]["content"], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), pinned_sha256)
                self.assertEqual(assets[name]["sha256"], pinned_sha256)

    def test_asset_sha_mismatch_holds_before_embedding(self):
        pins = list(operator.LIFELINE_OBSERVER_ASSET_PINS)
        name, path, _, max_bytes = pins[0]
        pins[0] = (name, path, "0" * 64, max_bytes)
        with patch.object(operator, "LIFELINE_OBSERVER_ASSET_PINS", tuple(pins)):
            with self.assertRaisesRegex(RuntimeError, "HOLD_LIFELINE_ASSET_PIN"):
                operator.build_lifeline_observer_bundle()


if __name__ == "__main__":
    unittest.main()
