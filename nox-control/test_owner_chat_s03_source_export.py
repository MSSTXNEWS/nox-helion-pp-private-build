import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import builtins
import sys
from unittest import mock
import zipfile
from io import BytesIO, StringIO

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False

ROOT = Path(__file__).parent


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_module("nox415_export_helper", ROOT / "owner_chat_s03_source_export.py")
operator = load_module("nox415_operator", ROOT / "owner_native_operator.py")


@unittest.skipUnless(HAS_CRYPTO, "cryptography unavailable")
class SourceExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        cls.pem = cls.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        cls.now = 1795101600
        cls.key_info = {
            "schema": "NOX_OWNER_SOURCE_EXPORT_KEY_V1",
            "scope": "NOX_S03_SOURCE_EXPORT_V1",
            "key_id": "unit-test-key",
            "transfer_id": "f" * 32,
            "created_at": cls.now,
            "expires_at": cls.now + 1800,
            "public_key_pem": cls.pem,
        }
        cls.key_encoded = base64.urlsafe_b64encode(helper.canonical(cls.key_info)).decode().rstrip("=")

    def sources(self):
        values = []
        for name, raw in (("chat_proxy.py", b"private-source-alpha"), ("s03_memory.py", b"private-source-beta")):
            values.append((name, raw, hashlib.sha256(raw).hexdigest(), None))
        return values

    def test_roundtrip_contains_exact_sources_only_after_decrypt(self):
        source_sha = "a" * 40
        encoded, receipt = helper.make_envelope(
            self.key_encoded, 123456, source_sha, self.sources(),
            schema={"status": "UNRESOLVED_STATIC_DB_PATH"}, now=self.now,
        )
        self.assertNotIn(b"private-source-alpha", encoded)
        self.assertNotIn(b"private-source-beta", encoded)
        envelope = json.loads(encoded)
        self.assertEqual(envelope["schema"], "NOX_ENCRYPTED_SOURCE_EXPORT_ENVELOPE_V1")
        aad = base64.b64decode(envelope["aad_b64"])
        wrapped = base64.b64decode(envelope["wrapped_key_b64"])
        aes_key = self.private.decrypt(
            wrapped,
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        plain = AESGCM(aes_key).decrypt(base64.b64decode(envelope["nonce_b64"]),
                                        base64.b64decode(envelope["ciphertext_b64"]), aad)
        self.assertEqual(hashlib.sha256(plain).hexdigest(), envelope["bundle_sha256"])
        with zipfile.ZipFile(BytesIO(plain)) as archive:
            self.assertEqual(archive.read("chat_proxy.py"), b"private-source-alpha")
            self.assertEqual(archive.read("s03_memory.py"), b"private-source-beta")
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["request_id"], 123456)
        self.assertEqual(manifest["source_sha"], source_sha)
        self.assertEqual(receipt["envelope_sha256"], hashlib.sha256(encoded).hexdigest())

    def test_owner_operator_reassembles_only_bound_ciphertext(self):
        source_sha = "b" * 40
        encoded, _ = helper.make_envelope(
            self.key_encoded, 123457, source_sha, self.sources(),
            schema={"status": "UNRESOLVED_STATIC_DB_PATH"}, now=self.now,
        )
        envelope = json.loads(encoded)
        total = (len(encoded) + helper.CHUNK_BYTES - 1) // helper.CHUNK_BYTES
        meta = {"schema": "NOX_SOURCE_EXPORT_TRANSFER_V1", "request_id": 123457,
                "source_sha": source_sha, "transfer_id": self.key_info["transfer_id"],
                "key_id": self.key_info["key_id"], "total_bytes": len(encoded),
                "total_chunks": total, "envelope_sha256": hashlib.sha256(encoded).hexdigest()}
        lines = [operator.SOURCE_EXPORT_META + json.dumps(meta, sort_keys=True, separators=(",", ":"))]
        for index in range(total):
            chunk = encoded[index * helper.CHUNK_BYTES:(index + 1) * helper.CHUNK_BYTES]
            lines.append(operator.SOURCE_EXPORT_CHUNK + json.dumps({
                "transfer_id": self.key_info["transfer_id"], "index": index,
                "data_b64": base64.b64encode(chunk).decode()}, sort_keys=True, separators=(",", ":")))
        lines.append(operator.SOURCE_EXPORT_COMPLETE)
        parsed_meta, parsed = operator.collect_source_export_stdout("\n".join(lines), 123457, source_sha)
        self.assertEqual(parsed, encoded)
        self.assertEqual(parsed_meta["request_id"], 123457)
        self.assertNotIn(b"private-source-alpha", parsed)
        with self.assertRaisesRegex(RuntimeError, "REQUEST_BINDING"):
            operator.collect_source_export_stdout("\n".join(lines), 999999, source_sha)

    def test_key_expiry_and_private_material_rejected(self):
        self.assertEqual(operator.source_export_key_info(self.key_encoded, now=self.now)["key_id"], "unit-test-key")
        with self.assertRaisesRegex(ValueError, "KEY_INVALID"):
            helper.load_export_key(self.key_encoded, now=self.now + 1801)
        private_info = dict(self.key_info, public_key_pem=self.private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode("ascii"))
        encoded = base64.urlsafe_b64encode(helper.canonical(private_info)).decode().rstrip("=")
        with self.assertRaisesRegex(ValueError, "KEY_INVALID"):
            helper.load_export_key(encoded, now=self.now)

    def test_sqlite_path_requires_static_source_expression(self):
        static = b"from pathlib import Path\nDB_PATH = Path('/root/nox/kb') / 'knowledge.sqlite'\nconn = sqlite3.connect(DB_PATH)\n"
        dynamic = b"import os, sqlite3\nDB_PATH = os.environ['NOX_DB']\nconn = sqlite3.connect(DB_PATH)\n"
        self.assertEqual(helper.resolve_db_path(static), "/root/nox/kb/knowledge.sqlite")
        self.assertIsNone(helper.resolve_db_path(dynamic))

    def test_pinned_provider_manifest_and_import(self):
        self.assertTrue(operator.verify_source_export_dependencies())
        import sys
        repo_root = ROOT.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe
        self.assertTrue(callable(ephemeral_ssh_probe.api))
        self.assertTrue(callable(ephemeral_ssh_probe.match))
        self.assertTrue(callable(ephemeral_ssh_probe.cleanup))
        self.assertEqual(ephemeral_ssh_probe.INSTANCE_ID, 60509551)

    def test_failed_preflight_or_provider_import_never_loads_owner_credential(self):
        original_import = builtins.__import__
        for failure in ("authorization", "dependency", "provider_import"):
            with self.subTest(failure=failure):
                attempted_provider_imports = []

                def guard_provider_import(name, *args, **kwargs):
                    if name.startswith("nox_runpod"):
                        attempted_provider_imports.append(name)
                        if failure == "provider_import":
                            raise RuntimeError("HOLD_TEST_PROVIDER_IMPORT")
                        raise AssertionError("provider import ran before precheck")
                    return original_import(name, *args, **kwargs)

                auth_patch = (
                    mock.patch.object(operator, "authorize_event",
                                      side_effect=RuntimeError("HOLD_OWNER_COMMAND_IDENTITY"))
                    if failure == "authorization"
                    else mock.patch.object(operator, "authorize_event", return_value=123458)
                )
                dependency_patch = (
                    mock.patch.object(operator, "verify_source_export_dependencies",
                                      side_effect=RuntimeError("HOLD_SOURCE_EXPORT_DEPENDENCY_MANIFEST_HASH"))
                    if failure == "dependency"
                    else mock.patch.object(operator, "verify_source_export_dependencies",
                                      return_value=True)
                    if failure == "provider_import"
                    else mock.patch.object(operator, "verify_source_export_dependencies",
                                      side_effect=AssertionError("dependency check ran before owner authorization"))
                )
                original_path = list(sys.path)
                safe_env = dict(os.environ)
                safe_env.pop("NOX2", None)
                safe_env["NOX2_FILE"] = "/tmp/nox2-s03-unused"
                safe_env["NOX_OWNER_EXPORT_KEY_B64"] = "public-key"
                with (
                    mock.patch.object(sys, "argv",
                                      ["owner_native_operator.py", "source_export"]),
                    mock.patch.dict(os.environ, safe_env, clear=True),
                    mock.patch.object(operator, "source_export_key_info", return_value={}),
                    mock.patch.object(operator, "load_source_export_credential_file") as load_credential,
                    auth_patch,
                    dependency_patch,
                    mock.patch.object(operator, "MASTER", None),
                    mock.patch("builtins.__import__", side_effect=guard_provider_import),
                    mock.patch("builtins.print"),
                ):
                    result = operator.main()
                    self.assertNotIn("NOX2", os.environ)

                self.assertEqual(result, 2)
                load_credential.assert_not_called()
                self.assertEqual(
                    attempted_provider_imports,
                    ["nox_runpod.teacher_mesh.v51"] if failure == "provider_import" else [],
                )
                if failure != "provider_import":
                    self.assertEqual(sys.path, original_path)

    def test_operator_rejects_cli_export_key_argument(self):
        with mock.patch("sys.stderr", new=StringIO()):
            with self.assertRaises(SystemExit):
                operator.operator_argument_parser().parse_args(["source_export", "public-key"])

    def test_export_key_preflight_is_secret_only_and_fails_closed(self):
        current = int(__import__("time").time())
        fresh_info = dict(self.key_info, created_at=current, expires_at=current + 1800)
        fresh_key = base64.urlsafe_b64encode(helper.canonical(fresh_info)).decode().rstrip("=")
        stdout = StringIO()
        stderr = StringIO()
        with mock.patch.object(operator.subprocess, "run") as run, \
                mock.patch.object(operator.subprocess, "check_output") as check_output, \
                mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "HOLD_SOURCE_EXPORT_KEY_UNAVAILABLE"):
                    operator.preflight_source_export_key()
            with mock.patch.dict(os.environ, {"NOX_OWNER_EXPORT_KEY_B64": "not-a-key"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "HOLD_SOURCE_EXPORT_KEY"):
                    operator.preflight_source_export_key()
            with mock.patch.dict(os.environ, {"NOX_OWNER_EXPORT_KEY_B64": fresh_key}, clear=True):
                self.assertEqual(operator.preflight_source_export_key(), fresh_key)
        run.assert_not_called()
        check_output.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_staged_owner_credential_is_private_single_use_and_never_env_injected(self):
        token = "test-owner-api-token"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nox2-s03-123456-1"
            path.write_text(token, encoding="ascii")
            path.chmod(0o600)
            with mock.patch.dict(os.environ, {
                "RUNNER_TEMP": td,
                "NOX2_FILE": str(path),
            }, clear=True):
                self.assertEqual(operator.load_source_export_credential_file(), token)
                self.assertFalse(path.exists())
                self.assertNotIn("NOX2", os.environ)

    def test_child_process_environments_never_receive_owner_secrets(self):
        token = "test-owner-api-token"
        export_key = "test-export-key-payload"
        with mock.patch.dict(os.environ, {"NOX2": token,
                                          "NOX_OWNER_EXPORT_KEY_B64": export_key,
                                          "SAFE_MARKER": "present"}, clear=True):
            with mock.patch.object(operator.subprocess, "run", return_value=mock.sentinel.child) as run:
                self.assertIs(operator._safe_subprocess_run(["ssh-keygen"]), mock.sentinel.child)
            run_env = run.call_args.kwargs["env"]
            self.assertNotIn("NOX2", run_env)
            self.assertNotIn("NOX_OWNER_EXPORT_KEY_B64", run_env)
            self.assertEqual(run_env["SAFE_MARKER"], "present")

            with mock.patch.object(operator.subprocess, "check_output", return_value="head") as check_output:
                self.assertEqual(operator._safe_subprocess_check_output(["git", "rev-parse"]), "head")
            check_env = check_output.call_args.kwargs["env"]
            self.assertNotIn("NOX2", check_env)
            self.assertNotIn("NOX_OWNER_EXPORT_KEY_B64", check_env)
            self.assertEqual(check_env["SAFE_MARKER"], "present")

    def test_provider_cleanup_uses_explicit_token_without_environment(self):
        import sys
        repo_root = ROOT.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as provider

        token = "test-owner-api-token"
        with tempfile.TemporaryDirectory() as td:
            runner = Path(td)
            tracked_file = runner / "tracked.json"
            tracked_file.write_text(json.dumps({"public": "test-public-key", "key_id": 7}), encoding="utf-8")
            with (
                mock.patch.object(provider, "RUNNER", runner),
                mock.patch.object(provider, "TRACK", tracked_file),
                mock.patch.object(provider, "_valid_public_key", return_value=True),
                mock.patch.object(provider, "match", side_effect=[[7], []]) as match,
                mock.patch.object(provider, "api", return_value={"success": True}) as api,
                mock.patch.object(provider, "_remove_local_files", return_value=True),
                mock.patch.dict(os.environ, {}, clear=True),
            ):
                self.assertTrue(provider.cleanup(token))

        api.assert_called_once_with("DELETE", f"/instances/{provider.INSTANCE_ID}/ssh/7", token)
        self.assertEqual(match.call_args_list[0].args, (token, "test-public-key"))
        self.assertEqual(match.call_args_list[1].args, (token, "test-public-key"))

    def test_export_artifact_is_exclusive_and_private_mode(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.getcwd()
            os.chdir(td)
            try:
                operator.write_source_export_artifact(b"ciphertext-only")
                path = Path("artifacts/nox-s03-source-export.enc")
                self.assertEqual(path.read_bytes(), b"ciphertext-only")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                with self.assertRaises(FileExistsError):
                    operator.write_source_export_artifact(b"replacement")
                self.assertEqual(path.read_bytes(), b"ciphertext-only")
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
