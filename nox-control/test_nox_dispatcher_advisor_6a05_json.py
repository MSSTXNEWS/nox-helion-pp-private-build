"""6A05: an ambiguous source document must never yield a trusted owner telemetry receipt."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec = importlib.util.spec_from_file_location(
    "nox_dispatcher_advisor", Path(__file__).with_name("nox_dispatcher_advisor.py")
)
advisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(advisor)


class FailClosedOwnerJsonTests(unittest.TestCase):
    def read(self, raw):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "owner.json"
            path.write_text(raw, encoding="utf8")
            return advisor._read_snapshot_json(path)

    def test_duplicate_stop_is_rejected_before_assessment(self):
        with self.assertRaises(SystemExit) as caught:
            self.read('{"stop_active":true,"stop_active":false}')
        self.assertEqual(str(caught.exception), "HOLD_OWNER_TELEMETRY_JSON_INVALID")

    def test_nested_lease_and_queue_shadowing_rejected(self):
        for raw in (
            '{"native_queue":{"owner_lease_cas_verified":false,"owner_lease_cas_verified":true}}',
            '{"native_queue":{"active_claims":true},"native_queue":{"active_claims":false}}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(SystemExit) as caught:
                    self.read(raw)
                self.assertEqual(str(caught.exception), "HOLD_OWNER_TELEMETRY_JSON_INVALID")

    def test_nonfinite_and_nonobject_input_rejected(self):
        for raw in ('{"gpu":{"temperature_c":NaN}}',
                    '{"gpu":{"utilization_pct":Infinity}}',
                    '{"gpu":{"utilization_pct":-Infinity}}',
                    '[{"stop_active":false}]', '{"stop_active":'):
            with self.subTest(raw=raw):
                with self.assertRaises(SystemExit) as caught:
                    self.read(raw)
                self.assertEqual(str(caught.exception), "HOLD_OWNER_TELEMETRY_JSON_INVALID")

    def test_valid_json_keeps_exact_stop_and_nested_types(self):
        source={"stop_active":True,"native_queue":{"active_claims":False,
              "owner_lease_cas_verified":False},"gpu":{"utilization_pct":29.5}}
        self.assertEqual(self.read(json.dumps(source)),source)


if __name__ == "__main__":
    unittest.main()
