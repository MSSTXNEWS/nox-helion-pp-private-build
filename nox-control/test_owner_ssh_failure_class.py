"""Bounded read-only diagnostics for Vast owner SSH failures; no SSH/API calls."""
import ast
from pathlib import Path
import unittest

SOURCE = Path(__file__).with_name("owner_native_operator.py")
class SSHErrors(unittest.TestCase):
    def test_diagnostic_labels_without_sensitive_content(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_native")
        classifier = next(n for n in ast.walk(run) if isinstance(n, ast.FunctionDef) and n.name == "ssh_failure_class")
        ns = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[classifier], type_ignores=[])),
                     str(SOURCE), "exec"), ns)
        fn = ns["ssh_failure_class"]
        cases = {
            "root@host: Permission denied (publickey).": "PUBLICKEY_REJECTED",
            "Authentication refused: bad ownership or modes for file /root/.ssh/authorized_keys": "BAD_AUTHORIZED_KEYS_PERMISSIONS",
            "ssh: connect to host private.example port 21: Connection refused": "CONNECTION_REFUSED",
            "ssh: connect to host private.example port 21: Connection timed out": "CONNECTION_TIMEOUT",
            "mux_client_request_session: master session id: 2": "MUX_SOCKET_FAILURE",
            "Warning: Permanently added host RSA key": "UNKNOWN",
        }
        for message, label in cases.items():
            with self.subTest(label=label):
                self.assertEqual(fn(message), label)
                self.assertNotIn("example", fn(message))
                self.assertNotIn("root", fn(message))
        self.assertEqual(fn(None), "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
