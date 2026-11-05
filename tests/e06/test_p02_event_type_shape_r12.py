"""E06 R12: negative type-shape regression against the actual P02 events.v3 relay.

No mocked product implementation. Existing host event publisher is a benign spy;
actual P02 module must be imported from the repository checkout. This test is
SOURCE/COMPONENT only; it cannot establish WebView2 or Windows EXE acceptance.

python -m unittest discover -s tests/e06 -p test_p02_event_type_shape_r12.py -v
"""
from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P02 = ROOT / "Packages" / "P02" / "worker-python"
if not (P02 / "p02_host_admission.py").is_file():
    raise RuntimeError("NOX P02 owner source missing; test must not silently use a stub")
sys.path.insert(0, str(P02))

from p02_runtime import P02Error  # noqa: E402
from p02_capabilities import Identity  # noqa: E402
from p02_host_admission import NativeHostBinding, P02EventRelay, P02_TYPES  # noqa: E402


class NativeEventShapeR12(unittest.TestCase):
    def setUp(self):
        self.deliveries = []
        route_map = {name: "host.p02." + name for name in P02_TYPES}
        binding = NativeHostBinding(
            Identity("tenant", "owner", "core", "persona", "session"),
            True,
            frozenset(route_map.values()),
            route_map,
            lambda name, payload: self.deliveries.append((name, payload)),
        )
        self.relay = P02EventRelay(binding)

    def assert_managed_denial(self, event):
        with self.assertRaises(P02Error):
            self.relay.relay(event)
        self.assertEqual([], self.deliveries)

    def test_array_type_is_managed_hold(self):
        self.assert_managed_denial({"type": [], "run_id": uuid.uuid4().hex})

    def test_object_type_is_managed_hold(self):
        self.assert_managed_denial({"type": {}, "run_id": uuid.uuid4().hex})

    def test_null_type_is_managed_hold(self):
        self.assert_managed_denial({"type": None, "run_id": uuid.uuid4().hex})

    def test_numeric_type_is_managed_hold(self):
        self.assert_managed_denial({"type": 9, "run_id": uuid.uuid4().hex})

    def test_unknown_string_type_is_managed_hold(self):
        self.assert_managed_denial({"type": "unknown.event", "run_id": uuid.uuid4().hex})

    def test_actual_owner_relay_still_publishes_valid_sequence(self):
        run_id = uuid.uuid4().hex
        self.relay.relay({"type": "chat.start", "run_id": run_id, "model": "local:installed"})
        self.relay.relay({"type": "chat.complete", "run_id": run_id, "chars": 0})
        self.assertEqual(len(self.deliveries), 2)
        self.assertEqual(self.deliveries[0][0], "host.p02.chat.start")
        self.assertEqual(self.deliveries[1][0], "host.p02.chat.complete")


if __name__ == "__main__":
    unittest.main()
