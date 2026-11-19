from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import unittest


SOURCE = Path(__file__).with_name("owner_smart_chat_acceptance.py")
SPEC = importlib.util.spec_from_file_location("owner_smart_chat_acceptance", SOURCE)
assert SPEC and SPEC.loader
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


class CredentialPathAstShapeTests(unittest.TestCase):
    def test_shape_contains_only_node_type_and_bounded_structure(self):
        expr = ast.parse("Path(SECRETS / '/private/secret-file')").body[0].value
        shape = QA.safe_ast_shape(expr)
        rendered = json.dumps(shape, sort_keys=True)
        self.assertNotIn("SECRETS", rendered)
        self.assertNotIn("/private/secret-file", rendered)
        self.assertLessEqual(shape["node_count"], 64)
        self.assertLessEqual(shape["max_depth"], 12)
        self.assertEqual(set(shape), {"node_count", "max_depth", "truncated", "nodes"})
        for row in shape["nodes"]:
            self.assertEqual(set(row), {"type", "depth", "children"})
            self.assertRegex(row["type"], r"^[A-Za-z]{1,32}$")
            self.assertIsInstance(row["depth"], int)
            self.assertIsInstance(row["children"], int)

    def test_nonstatic_hold_carries_only_redacted_ast_shape(self):
        expr = ast.parse("load_secret('/private/secret-file', TOKEN_NAME)").body[0].value
        error = QA.credential_path_not_static(expr)
        rendered = json.dumps({"outcome": str(error), "shape": error.safe_ast_shape})
        self.assertEqual(str(error), "HOLD_SMART_CHAT_QA_CREDENTIAL_PATH_NOT_STATIC")
        self.assertNotIn("/private/secret-file", rendered)
        self.assertNotIn("TOKEN_NAME", rendered)
        self.assertNotIn("load_secret", rendered)

    def test_static_path_hold_transfers_only_sanitized_shape_to_receipt(self):
        expr = ast.parse("resolve_password('/private/secret-token', CREDENTIAL_NAME)").body[0].value
        error = QA.credential_path_not_static(expr)
        status = {"outcome": str(error)}
        QA.add_credential_path_ast_shape(status, error)
        receipt = {"kind": "smart_chat_owner_e2e_qa", "data": status}
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertEqual(status["outcome"], "HOLD_SMART_CHAT_QA_CREDENTIAL_PATH_NOT_STATIC")
        self.assertIn("credential_path_ast_shape", status)
        self.assertNotIn("resolve_password", rendered)
        self.assertNotIn("/private/secret-token", rendered)
        self.assertNotIn("CREDENTIAL_NAME", rendered)
        shape = status["credential_path_ast_shape"]
        self.assertLessEqual(shape["node_count"], 64)
        self.assertLessEqual(max(row["children"] for row in shape["nodes"]), 64)

    def test_unresolved_name_receipt_uses_only_binding_enum_and_scope(self):
        expr = ast.parse("PRIVATE_BINDING_IDENTIFIER").body[0].value
        diagnostic = QA.safe_name_binding_diagnostic(
            expr.id, seen=(), definitions={}, common_defs={}, scope="proxy")
        error = QA.credential_path_not_static(expr, diagnostic)
        status = {"outcome": str(error)}
        QA.add_credential_path_ast_shape(status, error)
        receipt_text = json.dumps(status, sort_keys=True)
        self.assertEqual(status["credential_path_name_binding"], {
            "binding_state": "unbound", "scope": "proxy"})
        self.assertNotIn("PRIVATE_BINDING_IDENTIFIER", receipt_text)
        self.assertNotIn("PRIVATE_BINDING_IDENTIFIER", json.dumps(error.safe_ast_shape))

    def test_binding_enum_classifies_without_serializing_identifiers(self):
        secret_name = "REDACTED_ALIAS"
        cases = (
            ((), {secret_name: object()}, {}, "proxy", "defined"),
            ((), {}, {}, "proxy", "unbound"),
            ((secret_name,), {secret_name: object()}, {}, "proxy", "cycle"),
            ((), {}, {secret_name: object()}, "proxy", "ambiguous"),
            ((), {}, {}, "local", "unbound"),
            ((), {}, {}, "common", "unbound"),
        )
        for seen, definitions, common_defs, scope, expected in cases:
            with self.subTest(scope=scope, expected=expected):
                result = QA.safe_name_binding_diagnostic(
                    secret_name, seen, definitions, common_defs, scope)
                self.assertEqual(result["binding_state"], expected)
                self.assertEqual(result["scope"], scope)
                self.assertEqual(set(result), {"binding_state", "scope"})
                self.assertNotIn(secret_name, json.dumps(result))

    def test_shape_is_bounded_for_large_ast(self):
        expr = ast.parse("f(" + ",".join("x" for _ in range(100)) + ")").body[0].value
        shape = QA.safe_ast_shape(expr, max_nodes=8, max_depth=12)
        self.assertEqual(shape["node_count"], 8)
        self.assertLessEqual(max(row["children"] for row in shape["nodes"]), 8)
        self.assertTrue(shape["truncated"])


if __name__ == "__main__":
    unittest.main()
