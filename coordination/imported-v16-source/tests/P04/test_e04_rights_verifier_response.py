"""Source-module checks for P04 fail-closed rights-verifier JSON semantics.
No model weights, GPU, network, fake training, or permissions are implied.
"""
import importlib.util
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[2] / "Packages" / "P04" / "train_qlora.py"
spec = importlib.util.spec_from_file_location("nox_p04_rights_gate_under_test", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RightsVerifierResponseTests(unittest.TestCase):
    def test_valid_object(self):
        self.assertEqual(module.parse_rights_verifier_response(
            '{"status":"VERIFIED","metadata":{"audit":1}}')["status"], "VERIFIED")

    def test_duplicate_top_level_denial(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_KEY"):
            module.parse_rights_verifier_response('{"status":"DENIED","status":"VERIFIED"}')

    def test_duplicate_nested_identity(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_KEY"):
            module.parse_rights_verifier_response('{"metadata":{"approval":1,"approval":2}}')

    def test_nan(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            module.parse_rights_verifier_response('{"score":NaN}')

    def test_infinity(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            module.parse_rights_verifier_response('{"score":-Infinity}')

    def test_float_overflow(self):
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            module.parse_rights_verifier_response('{"score":1e9999}')

    def test_non_object_response(self):
        with self.assertRaisesRegex(ValueError, "INVALID_RESPONSE"):
            module.parse_rights_verifier_response('[]')

    def test_malformed_json(self):
        with self.assertRaisesRegex(ValueError, "INVALID_RESPONSE"):
            module.parse_rights_verifier_response('{invalid}')

    def test_oversized_response(self):
        with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
            module.parse_rights_verifier_response('x' * 65537)


if __name__ == "__main__":
    unittest.main()
