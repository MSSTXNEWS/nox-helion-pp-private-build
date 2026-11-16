"""Portable checks for the fixed server verifier embedded in the PC bootstrap.

These tests execute the Python verifier with isolated files/mocked SSH. They do
not pretend to execute Windows services, ACLs, DPAPI or Task Scheduler.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import types
import unittest
from unittest import mock


SOURCE = Path(__file__).with_name("NOX_CONNECT_PC.ps1").read_text()
REMOTE = re.search(r"\$RemoteControl = @'\n(.*?)\n'@", SOURCE, re.S).group(1)


class PcBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.code = {"__name__": "nox_pc_verifier_test"}
        exec(compile(REMOTE, "NOX_CONNECT_PC.remote.py", "exec"), self.code)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.state.chmod(0o700)
        self.code["STATE"] = self.state
        self.code["CONNECTION"] = self.state / "connection.json"
        blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))
        public = "ssh-ed25519 " + base64.b64encode(blob).decode()
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        self.data = {
            "schema": "NOX_PC_LINK_V1", "instance_id": 60509551,
            "reverse_host": "127.0.0.1", "reverse_port": 46051,
            "pc_ssh_port": 2222, "pc_user": "owner", "pc_host_key": public,
            "pc_host_key_sha256": fingerprint, "backup_root": r"C:\NOX_HELION",
            "installation_id": "a" * 32, "pc_key_fingerprint": fingerprint,
            "reserve_bytes": 20 * 1024**3, "reserve_percent": 10,
        }

    def test_complete_valid_contract_and_fingerprint(self):
        self.assertIs(self.code["validate"](self.data), self.data)
        self.assertEqual(self.code["public_key"](self.data["pc_host_key"]), self.data["pc_host_key_sha256"])

    def test_rejects_address_port_user_and_path_injection(self):
        changes = [
            ("reverse_host", "0.0.0.0"), ("reverse_port", 22),
            ("pc_ssh_port", True), ("pc_ssh_port", 0),
            ("pc_user", "owner\r\nAllowUsers *"), ("pc_user", "-oProxyCommand=bad"),
            ("backup_root", r"\\host\share"), ("backup_root", r"C:\NOX\..\Windows"),
            ("backup_root", "C:\\NOX\n"), ("installation_id", "../other"),
            ("instance_id", 1), ("pc_host_key_sha256", "SHA256:wrong"),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.data)
                data[field] = value
                with self.assertRaises(RuntimeError):
                    self.code["validate"](data)

    def test_public_key_checks_wire_format_not_just_prefix(self):
        with self.assertRaises(RuntimeError):
            self.code["public_key"]("ssh-ed25519 " + base64.b64encode(b"x" * 51).decode())

    def test_atomic_connection_has_private_permissions_and_no_temp_leak(self):
        target = self.state / "connection.json"
        self.code["atomic"](target, json.dumps(self.data))
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(json.loads(target.read_text()), self.data)
        self.code["atomic"](target, "{}\n")
        self.assertEqual(target.read_text(), "{}\n")
        self.assertEqual(sorted(x.name for x in self.state.iterdir()), ["connection.json"])

    def test_atomic_write_refuses_symlink(self):
        other = self.state / "unrelated"
        other.write_text("keep")
        target = self.state / "connection.json"
        target.symlink_to(other)
        with self.assertRaisesRegex(RuntimeError, "HOLD_STATE_SYMLINK"):
            self.code["atomic"](target, "replace")
        self.assertEqual(other.read_text(), "keep")

    def test_refuses_another_registered_pc(self):
        (self.state / "connection.json").write_text(json.dumps({"installation_id": "b" * 32}))
        with self.assertRaisesRegex(RuntimeError, "HOLD_OTHER_PC_REGISTRATION"):
            self.code["existing"]("a" * 32)

    def test_per_connection_match_overrides_global_forwarding(self):
        global_result = types.SimpleNamespace(returncode=0, stdout="usedns no\ngatewayports no\nallowtcpforwarding yes\n")
        match_result = types.SimpleNamespace(returncode=0, stdout="gatewayports yes\nallowtcpforwarding yes\ndisableforwarding no\n")
        with mock.patch.dict(os.environ, {"SSH_CONNECTION": "203.0.113.2 55000 172.17.0.2 22"}), \
             mock.patch.object(self.code["subprocess"], "run", side_effect=[global_result, match_result]) as run:
            with self.assertRaisesRegex(RuntimeError, "HOLD_PUBLIC_REVERSE_LISTENER"):
                self.code["forwarding"]()
            self.assertEqual(run.call_args_list[1].args[0][-1],
                             "user=root,addr=203.0.113.2,host=203.0.113.2,laddr=172.17.0.2,lport=22")

    def test_per_connection_remote_forwarding_allowed(self):
        global_result = types.SimpleNamespace(returncode=0, stdout="usedns no\n")
        match_result = types.SimpleNamespace(returncode=0, stdout="gatewayports clientspecified\nallowtcpforwarding remote\ndisableforwarding no\n")
        with mock.patch.dict(os.environ, {"SSH_CONNECTION": "203.0.113.2 55000 172.17.0.2 22"}), \
             mock.patch.object(self.code["subprocess"], "run", side_effect=[global_result, match_result]):
            self.assertTrue(self.code["forwarding"]())

    def test_actual_reverse_listener_rejects_wildcard(self):
        port = format(46051, "04X")
        for address, accepted in [("0100007F", True), ("00000000", False), ("0200007F", False)]:
            with self.subTest(address=address):
                tcp = "header\n0: " + address + ":" + port + " 00000000:0000 0A ignored\n"
                with mock.patch.object(Path, "read_text", side_effect=[tcp, "header\n"]):
                    if accepted:
                        self.code["listener"]()
                    else:
                        with self.assertRaisesRegex(RuntimeError, "HOLD_REVERSE_LISTENER_NOT_EXCLUSIVE_LOOPBACK"):
                            self.code["listener"]()

    def test_reverse_ssh_uses_exact_key_pin_and_never_exports_private_key(self):
        key = self.state / "operator_ed25519"
        key.write_text("test fixture, not a real secret")
        key.chmod(0o600)
        result = types.SimpleNamespace(returncode=0, stdout="NOX_PC_LINK_OK\r\n")
        with mock.patch.dict(self.code, {"listener": lambda: None}), \
             mock.patch.object(self.code["subprocess"], "run", return_value=result) as run:
            self.code["verify"](self.data)
            args = run.call_args.args[0]
            self.assertIn("StrictHostKeyChecking=yes", args)
            self.assertIn(str(key), args)
            self.assertIn("BatchMode=yes", args)
            self.assertEqual(args[-1], "cmd.exe /d /c echo NOX_PC_LINK_OK")
        self.assertEqual((self.state / "bootstrap_known_hosts").read_text(),
                         "[127.0.0.1]:46051 " + self.data["pc_host_key"] + "\n")
        # The only remote cat downloads the .pub path. No SCP fetches private keys.
        cats = re.findall(r"cat (/root/nox/[^'\s]+)", SOURCE)
        self.assertEqual(cats, ["/root/nox/state/pc_shell/operator_ed25519.pub"])

    def test_publish_requires_real_ssh_verification_before_connection_write(self):
        request = json.dumps({"action": "publish", "connection": self.data}).encode()
        fake_stdin = types.SimpleNamespace(buffer=__import__("io").BytesIO(request))
        with mock.patch.object(self.code["sys"], "stdin", fake_stdin), \
             mock.patch.dict(self.code, {"forwarding": lambda: True,
                                        "verify": mock.Mock(side_effect=RuntimeError("HOLD_PC_SSH_VERIFICATION"))}):
            with self.assertRaisesRegex(RuntimeError, "HOLD_PC_SSH_VERIFICATION"):
                self.code["main"]()
        self.assertFalse((self.state / "connection.json").exists())

    def test_successful_heartbeat_refreshes_private_server_status(self):
        previous = copy.deepcopy(self.data)
        previous.update(connected=False, connected_utc="2000-01-01T00:00:00+00:00",
                        owned_cold_pc_config_sha256="a" * 64)
        connection = self.state / "connection.json"
        connection.write_text(json.dumps(previous))
        request = json.dumps({"action": "verify", "connection": self.data}).encode()
        fake_stdin = types.SimpleNamespace(buffer=__import__("io").BytesIO(request))
        with mock.patch.object(self.code["sys"], "stdin", fake_stdin), \
             mock.patch.object(self.code["sys"], "stdout", __import__("io").StringIO()), \
             mock.patch.dict(self.code, {"forwarding": lambda: True, "verify": lambda _: None}):
            self.code["main"]()
        current = json.loads(connection.read_text())
        self.assertTrue(current["connected"])
        self.assertNotEqual(current["connected_utc"], previous["connected_utc"])
        self.assertEqual(current["last_verified_utc"], current["connected_utc"])
        self.assertEqual(current["owned_cold_pc_config_sha256"], "a" * 64)
        self.assertEqual(stat.S_IMODE(connection.stat().st_mode), 0o600)

    def test_heartbeat_rejects_changed_registration_before_ssh(self):
        previous = copy.deepcopy(self.data)
        previous["backup_root"] = r"D:\other"
        connection = self.state / "connection.json"
        connection.write_text(json.dumps(previous))
        request = json.dumps({"action": "verify", "connection": self.data}).encode()
        fake_stdin = types.SimpleNamespace(buffer=__import__("io").BytesIO(request))
        verifier = mock.Mock()
        with mock.patch.object(self.code["sys"], "stdin", fake_stdin), \
             mock.patch.dict(self.code, {"forwarding": lambda: True, "verify": verifier}):
            with self.assertRaisesRegex(RuntimeError, "HOLD_LINK_CONFIG_CHANGED"):
                self.code["main"]()
        verifier.assert_not_called()
        self.assertEqual(json.loads(connection.read_text()), previous)

    def test_windows_auth_and_task_security_invariants(self):
        self.assertIn("-LogonType Interactive -RunLevel Limited", SOURCE)
        self.assertIn("ConvertFrom-SecureString $secret", SOURCE)
        self.assertNotRegex(SOURCE, r"(?i)Register-ScheduledTask[^\n]*-Password")
        self.assertNotIn("New-NetFirewallRule", SOURCE)
        self.assertNotIn("Set-ExecutionPolicy", SOURCE)
        self.assertIn("no-agent-forwarding,no-port-forwarding,no-X11-forwarding", SOURCE)
        self.assertIn("Match User `\"$user`\" Address 127.0.0.1,::1", SOURCE)
        self.assertIn("$previousFiles", SOURCE)
        self.assertIn("HOLD_AUTHORIZED_KEYS_PRECEDENCE", SOURCE)
        self.assertIn("$process.StartTime.ToUniversalTime().Ticks -eq [long]$record.started_ticks", SOURCE)
        self.assertNotRegex(SOURCE, r"(?i)Stop-Process\s+-Name\s+ssh")


if __name__ == "__main__":
    unittest.main()
