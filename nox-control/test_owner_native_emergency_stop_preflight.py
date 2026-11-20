"""Source-only checks for the bounded read-only endpoint preflight."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).with_name("owner_native_emergency_stop_preflight.py")
SPEC = importlib.util.spec_from_file_location("owner_native_emergency_stop_preflight", SOURCE)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class EndpointPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.supervisor_dir = self.root / "etc" / "supervisor"
        self.include_dir = self.supervisor_dir / "conf.d"
        self.include_dir.mkdir(parents=True)
        self.main = self.supervisor_dir / "supervisord.conf"
        P.ROOT_UID = os.geteuid()
        P.SUPERVISOR_CLIENT_CONFIG = self.main
        P.SUPERVISOR_CONFIG_DIR = self.include_dir
        self.write_config("unix:///run/supervisor.sock")
        (self.include_dir / "nox.conf").write_text(
            "[program:nox-ds41-8098]\ncommand=/bin/true\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, serverurl: str, *, socket_file: str = "/run/supervisor.sock",
                     mode: str = "0700", owner: str = "root:root",
                     factory: str = "supervisor.rpcinterface:make_main_rpcinterface"):
        self.main.write_text(
            "[unix_http_server]\n"
            f"file={socket_file}\nchmod={mode}\nchown={owner}\n\n"
            "[rpcinterface:supervisor]\n"
            f"supervisor.rpcinterface_factory={factory}\n\n"
            "[supervisorctl]\n"
            f"serverurl={serverurl}\n\n"
            "[include]\n"
            f"files={self.include_dir}/*.conf\n",
            encoding="utf-8")

    def test_matching_endpoint_emits_only_fixed_safe_facts_and_hashes(self):
        receipt = P.inspect_configuration()
        endpoint = receipt["endpoint"]
        expected = hashlib.sha256(b"/run/supervisor.sock").hexdigest()
        self.assertEqual(endpoint["normalized_socket_path_sha256"], expected)
        self.assertEqual(endpoint["serverurl_path_sha256"], expected)
        self.assertNotIn("normalized_socket_path", endpoint)
        self.assertNotIn("serverurl_path", endpoint)
        self.assertTrue(endpoint["socket_serverurl_paths_equal"])
        self.assertTrue(endpoint["rpc_factory_matches_fixed_allowlist"])
        self.assertTrue(endpoint["configured_owner_is_root_root"])
        self.assertTrue(endpoint["configured_mode_format_allowed"])
        self.assertTrue(endpoint["configured_mode_private"])
        self.assertTrue(endpoint["configured_mode_owner_write_set"])
        self.assertTrue(endpoint["endpoint_config_predicates_all_pass"])
        for key, value in receipt["config"].items():
            if key.endswith("sha256"):
                self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["config"]["main_sha256"],
                         hashlib.sha256(self.main.read_bytes()).hexdigest())
        self.assertEqual(receipt["config"]["include_file_count"], 1)
        self.assertTrue(receipt["read_only"])
        self.assertEqual(receipt["host_writes"], 0)
        self.assertEqual(receipt["supervisor_rpc_calls"], 0)
        self.assertEqual(receipt["process_signals"], 0)
        self.assertFalse(receipt["raw_config_values_included"])

    def test_nonallowlisted_include_glob_denies_full_endpoint_attestation(self):
        # A correct UNIX endpoint must not certify an unreviewed program set.
        original = self.main.read_text(encoding="utf-8")
        expected = f"files={self.include_dir}/*.conf"
        self.assertEqual(original.count(expected), 1)
        self.main.write_text(original.replace(expected, "files=/tmp/unreviewed/*.conf"),
                             encoding="utf-8")
        receipt = P.inspect_configuration()
        self.assertFalse(receipt["include_glob_matches_fixed_scope"])
        self.assertFalse(receipt["endpoint"]["endpoint_config_predicates_all_pass"])
        self.assertEqual(receipt["host_writes"], 0)
        self.assertEqual(receipt["supervisor_rpc_calls"], 0)
        self.assertEqual(receipt["process_signals"], 0)

    def test_mismatched_endpoint_is_reported_without_approving_or_mutating(self):
        self.write_config("unix:///run/other.sock")
        receipt = P.inspect_configuration()
        endpoint = receipt["endpoint"]
        self.assertEqual(endpoint["normalized_socket_path_sha256"],
                         hashlib.sha256(b"/run/supervisor.sock").hexdigest())
        self.assertEqual(endpoint["serverurl_path_sha256"],
                         hashlib.sha256(b"/run/other.sock").hexdigest())
        self.assertFalse(endpoint["socket_serverurl_paths_equal"])
        self.assertFalse(endpoint["endpoint_config_predicates_all_pass"])
        self.assertEqual(receipt["host_writes"], 0)

    def test_snapshot_rejects_in_place_edits_to_already_read_files(self):
        first_include = self.include_dir / "nox.conf"
        last_include = self.include_dir / "z-last.conf"
        last_include.write_text("[program:other]\ncommand=/bin/true\n",
                                encoding="utf-8")
        original_read = P._read_root_regular

        for target in (self.main, first_include):
            with self.subTest(target=target.name):
                def read_and_edit(path, limit):
                    result = original_read(path, limit)
                    if path == last_include:
                        target.write_bytes(target.read_bytes() + b"\n# changed\n")
                    return result

                with patch.object(P, "_read_root_regular", side_effect=read_and_edit):
                    with self.assertRaisesRegex(RuntimeError,
                                                "HOLD_ENDPOINT_PREFLIGHT_CONFIG_FILE_CHANGED"):
                        P.inspect_configuration()

    def test_stock_inline_semicolon_comments_leave_exact_endpoint_values(self):
        self.write_config("unix:///var/run/supervisor.sock ; server URL",
                          socket_file="/var/run/supervisor.sock   ; socket file",
                          mode="0700 ; owner-only mode")
        receipt = P.inspect_configuration()
        endpoint = receipt["endpoint"]
        expected = hashlib.sha256(b"/var/run/supervisor.sock").hexdigest()
        self.assertEqual(endpoint["normalized_socket_path_sha256"], expected)
        self.assertEqual(endpoint["serverurl_path_sha256"], expected)
        self.assertTrue(endpoint["endpoint_config_predicates_all_pass"])
        self.assertEqual(receipt["config"]["main_sha256"],
                         hashlib.sha256(self.main.read_bytes()).hexdigest())

    def test_unseparated_semicolons_do_not_hide_invalid_endpoint_values(self):
        self.write_config("unix:///var/run/supervisor.sock;unexpected",
                          socket_file="/var/run/supervisor.sock;unexpected",
                          mode="0700;unexpected")
        endpoint = P.inspect_configuration()["endpoint"]
        self.assertFalse(endpoint["socket_path_absolute_no_traversal"])
        self.assertFalse(endpoint["configured_mode_format_allowed"])
        self.assertFalse(endpoint["endpoint_config_predicates_all_pass"])

    def test_secret_bearing_serverurl_is_never_echoed(self):
        secret = "do-not-emit-this-token"
        self.write_config(f"unix:///run/supervisor.sock?token={secret}")
        rendered = json.dumps(P.inspect_configuration(), sort_keys=True)
        self.assertNotIn(secret, rendered)
        receipt = json.loads(rendered)
        self.assertEqual(receipt["endpoint"]["serverurl_path_sha256"],
                         hashlib.sha256(b"/run/supervisor.sock").hexdigest())
        self.assertFalse(receipt["endpoint"]["serverurl_has_no_authority_query_fragment"])
        self.assertFalse(receipt["endpoint"]["endpoint_config_predicates_all_pass"])

    def test_token_like_path_suffix_is_only_exposed_as_digest(self):
        secret = "credential-shaped-suffix-43fa91"
        path = "/run/supervisor.sock/" + secret
        self.write_config("unix://" + path, socket_file=path)
        receipt = P.inspect_configuration()
        rendered = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(secret, rendered)
        self.assertNotIn(path, rendered)
        self.assertTrue(receipt["endpoint"]["socket_serverurl_paths_equal"])
        expected = hashlib.sha256(path.encode("utf-8")).hexdigest()
        self.assertEqual(receipt["endpoint"]["normalized_socket_path_sha256"], expected)
        self.assertEqual(receipt["endpoint"]["serverurl_path_sha256"], expected)

    def test_non_allowlisted_factory_owner_and_mode_fail_closed_as_facts(self):
        self.write_config("unix:///run/supervisor.sock", mode="0777",
                          owner="nox:nox", factory="example:factory")
        endpoint = P.inspect_configuration()["endpoint"]
        self.assertFalse(endpoint["rpc_factory_matches_fixed_allowlist"])
        self.assertFalse(endpoint["configured_owner_is_root_root"])
        self.assertFalse(endpoint["configured_mode_private"])
        self.assertFalse(endpoint["endpoint_config_predicates_all_pass"])

    def test_path_traversal_and_unknown_interpolation_are_redacted(self):
        self.write_config("unix:///run/../etc/passwd",
                          socket_file="%(ENV_SECRET)s/endpoint.sock")
        endpoint = P.inspect_configuration()["endpoint"]
        self.assertFalse(endpoint["socket_path_absolute_no_traversal"])
        self.assertTrue(endpoint["serverurl_path_sha256"])
        self.assertFalse(endpoint["socket_serverurl_paths_equal"])
        self.assertFalse(endpoint["endpoint_config_predicates_all_pass"])

    def test_source_has_no_process_network_rpc_or_write_apis(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"subprocess", "signal", "fcntl", "socket", "xmlrpc"})
        calls = {node.func.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & {"write_text", "write_bytes", "unlink", "flock",
                                  "kill", "connect", "urlopen", "Popen", "run"})


if __name__ == "__main__":
    unittest.main()
