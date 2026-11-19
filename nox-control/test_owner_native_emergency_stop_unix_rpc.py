import importlib.util
import configparser
from pathlib import Path
import struct
import unittest
from unittest import mock
import xmlrpc.client


SOURCE = Path(__file__).with_name("owner_native_emergency_stop.py")
SPEC = importlib.util.spec_from_file_location("owner_native_emergency_stop_under_test", SOURCE)
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)


class UnixSupervisorRpcTests(unittest.TestCase):
    def setUp(self):
        self.old = (OWNER.SUPERVISORCTL_BIN, OWNER.SUPERVISORCTL_SELECTED_IDENTITY,
                    OWNER.SUPERVISORCTL_SELECTED_DAEMON_IDENTITY,
                    OWNER.SUPERVISORCTL_TRANSPORT, OWNER.SUPERVISOR_UNIX_ENDPOINT,
                    OWNER.SUPERVISOR_RPC_STOP_DISPATCHED,
                    OWNER.STOP_REQUEST_DISPATCHED,
                    OWNER.DIAGNOSTICS.get("supervisorctl_client"))
        self.endpoint = {"daemon": {"pid": 42},
                         "socket": {"resolved_path": "/run/test-supervisor.sock"}}
        self.identity = {"transport": "supervisor_unix_xmlrpc",
                         "path": "/run/test-supervisor.sock", "sha256": "a" * 64}
        OWNER.SUPERVISORCTL_BIN = None
        OWNER.SUPERVISORCTL_SELECTED_IDENTITY = self.identity
        OWNER.SUPERVISORCTL_SELECTED_DAEMON_IDENTITY = self.endpoint["daemon"]
        OWNER.SUPERVISORCTL_TRANSPORT = "unix_xmlrpc"
        OWNER.SUPERVISOR_UNIX_ENDPOINT = self.endpoint
        OWNER.SUPERVISOR_RPC_STOP_DISPATCHED = False
        OWNER.STOP_REQUEST_DISPATCHED = False
        OWNER.DIAGNOSTICS["supervisorctl_client"] = self.identity

    def tearDown(self):
        (OWNER.SUPERVISORCTL_BIN, OWNER.SUPERVISORCTL_SELECTED_IDENTITY,
         OWNER.SUPERVISORCTL_SELECTED_DAEMON_IDENTITY,
         OWNER.SUPERVISORCTL_TRANSPORT, OWNER.SUPERVISOR_UNIX_ENDPOINT,
         OWNER.SUPERVISOR_RPC_STOP_DISPATCHED,
         OWNER.STOP_REQUEST_DISPATCHED, prior_client) = self.old
        if prior_client is None:
            OWNER.DIAGNOSTICS.pop("supervisorctl_client", None)
        else:
            OWNER.DIAGNOSTICS["supervisorctl_client"] = prior_client

    def test_pid_command_uses_read_only_xmlrpc(self):
        with mock.patch.object(OWNER, "_supervisor_unix_rpc", return_value=42) as rpc:
            result = OWNER.command(["supervisorctl", "-c",
                                    str(OWNER.SUPERVISOR_CLIENT_CONFIG), "pid"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "42\n")
        rpc.assert_called_once_with(self.endpoint, "supervisor.getPID", (), 15)

    def test_status_command_maps_only_exact_model_process(self):
        info = {"name": OWNER.SUPERVISOR_SERVICE, "statename": "RUNNING",
                "pid": OWNER.MODEL_PID}
        with mock.patch.object(OWNER, "_supervisor_unix_rpc", return_value=info):
            result = OWNER.command(["supervisorctl", "-c",
                                    str(OWNER.SUPERVISOR_CLIENT_CONFIG),
                                    "status", OWNER.SUPERVISOR_SERVICE])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout,
                         f"{OWNER.SUPERVISOR_SERVICE} RUNNING pid {OWNER.MODEL_PID}\n")

    def test_stop_command_allows_only_exact_service_and_waits(self):
        info = {"name": OWNER.SUPERVISOR_SERVICE, "statename": "RUNNING",
                "pid": OWNER.MODEL_PID}
        with (mock.patch.object(OWNER, "_supervisor_unix_rpc",
                                side_effect=[info, True]) as rpc,
              mock.patch.object(OWNER, "stable_start_ticks",
                                return_value=OWNER.MODEL_START_TICKS)):
            result = OWNER.command(["supervisorctl", "-c",
                                    str(OWNER.SUPERVISOR_CLIENT_CONFIG),
                                    "stop", OWNER.SUPERVISOR_SERVICE],
                                   verified_client_sha256=self.identity["sha256"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(rpc.call_args.args[1:3],
                         ("supervisor.stopProcess",
                          (OWNER.SUPERVISOR_SERVICE, True)))

    def test_uds_stop_transport_exception_is_marked_dispatched(self):
        info = {"name": OWNER.SUPERVISOR_SERVICE, "statename": "RUNNING",
                "pid": OWNER.MODEL_PID}
        with (mock.patch.object(OWNER, "_supervisor_unix_rpc",
                                side_effect=[info, OSError("lost reply")]),
              mock.patch.object(OWNER, "stable_start_ticks",
                                return_value=OWNER.MODEL_START_TICKS)):
            with self.assertRaisesRegex(OSError, "lost reply"):
                OWNER.command(["supervisorctl", "-c",
                               str(OWNER.SUPERVISOR_CLIENT_CONFIG),
                               "stop", OWNER.SUPERVISOR_SERVICE])
        self.assertTrue(OWNER.STOP_REQUEST_DISPATCHED)

    def test_subprocess_spawn_exception_is_marked_dispatched(self):
        OWNER.SUPERVISORCTL_TRANSPORT = "supervisorctl"
        OWNER.SUPERVISORCTL_BIN = Path("/usr/bin/supervisorctl")
        argv = ["supervisorctl", "-c", str(OWNER.SUPERVISOR_CLIENT_CONFIG),
                "stop", OWNER.SUPERVISOR_SERVICE]
        with (mock.patch.object(OWNER, "verify_supervisorctl_executable",
                                return_value=self.identity),
              mock.patch.object(OWNER, "invoke_supervisorctl_path",
                                side_effect=OSError("spawn outcome unknown"))):
            with self.assertRaisesRegex(OSError, "spawn outcome unknown"):
                OWNER.command(argv)
        self.assertTrue(OWNER.STOP_REQUEST_DISPATCHED)

    def test_dispatched_stop_reconciles_read_only_without_retry(self):
        status = {"state": "STOPPED", "pid": None}
        pid_state = {"pinned_pid_absent": True}
        with (mock.patch.object(OWNER, "wait_model_stopped", return_value=status) as wait,
              mock.patch.object(OWNER, "require_model_identity_gone",
                                return_value=pid_state) as identity_gone):
            self.assertEqual(OWNER.reconcile_dispatched_stop_without_retry(),
                             (status, pid_state))
        wait.assert_called_once_with()
        identity_gone.assert_called_once_with()
        self.assertEqual(OWNER.DIAGNOSTICS["stop_action_outcome"],
                         "NO_ACK_POST_STOP_STATE_CONFIRMED")

    def test_socket_rpc_checks_peer_and_bounds_response_without_host_io(self):
        body = xmlrpc.client.dumps((42,), methodresponse=True).encode("utf-8")
        response = (b"HTTP/1.0 200 OK\r\nContent-Type: text/xml\r\nContent-Length: " +
                    str(len(body)).encode("ascii") + b"\r\n\r\n" + body)

        class FakeSocket:
            def __init__(self):
                self.response = response
                self.request = b""

            def settimeout(self, _seconds):
                pass

            def connect(self, path):
                self.path = path

            def getsockopt(self, *_args):
                return struct.pack("3i", 42, 0, 0)

            def sendall(self, value):
                self.request += value

            def recv(self, _size):
                value, self.response = self.response, b""
                return value

            def close(self):
                pass

        fake = FakeSocket()
        with (mock.patch.object(OWNER, "_supervisor_unix_endpoint_snapshot",
                                return_value=self.endpoint),
              mock.patch.object(OWNER, "_verify_unix_rpc_peer"),
              mock.patch.object(OWNER.os, "pidfd_open", return_value=123),
              mock.patch.object(OWNER.os, "close"),
              mock.patch.object(OWNER.socket, "socket", return_value=fake)):
            value = OWNER._supervisor_unix_rpc(self.endpoint, "supervisor.getPID", ())
        self.assertEqual(value, 42)
        self.assertIn(b"POST /RPC2 HTTP/1.0", fake.request)
        self.assertFalse(OWNER.SUPERVISOR_RPC_STOP_DISPATCHED)

    def test_peer_credentials_reject_wrong_pid_uid_and_gid(self):
        endpoint = {"daemon": {"pid": 42}}

        class CredSocket:
            def __init__(self, credential):
                self.credential = credential

            def getsockopt(self, *_args):
                return struct.pack("3i", *self.credential)

        for credential in ((99, 0, 0), (42, 1000, 0), (42, 0, 1000)):
            with self.subTest(credential=credential):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_EMERGENCY_STOP_UNIX_RPC_PEERCRED_MISMATCH"):
                    OWNER._verify_unix_rpc_peer(CredSocket(credential), endpoint)

    def _peer_endpoint_for_validation(self):
        daemon = {"pid": 42, "start_ticks": 77, "config_path": str(
            OWNER.SUPERVISOR_CLIENT_CONFIG), "argv_sha256": "c" * 64}
        socket_identity = {"resolved_path": "/run/test.sock", "inode": 11,
                           "device": 1}
        config_identity = {"effective_config_sha256": "d" * 64}
        linkage = {"filesystem_socket_inode": 11,
                   "filesystem_socket_device": 1,
                   "kernel_listener_inode": 123,
                   "peer_fd_numbers": ["4"],
                   "peer_start_ticks": 77, "net_unix_path_rows": [
                       {"kernel_inode": 123, "path": "/run/test.sock",
                        "type": "0001", "state": "01"}]}
        return {"daemon": daemon, "socket": socket_identity,
                "config_identity": config_identity,
                "socket_linkage": linkage}

    def test_path_inode_is_distinct_from_kernel_listener_inode(self):
        net = ("Num RefCount Protocol Flags Type St Inode Path\n"
               "0000000000000000: 00000002 00000000 00010000 0001 01 123 /run/test.sock\n")
        rows = OWNER._parse_unix_socket_listener_rows(net, "/run/test.sock")
        self.assertEqual(rows[0]["kernel_inode"], 123)
        endpoint = self._peer_endpoint_for_validation()
        self.assertEqual(endpoint["socket"]["inode"], 11)
        self.assertNotEqual(endpoint["socket"]["inode"], rows[0]["kernel_inode"])

    def test_duplicate_missing_and_non_listener_rows_hold(self):
        header = "Num RefCount Protocol Flags Type St Inode Path\n"
        good = "0000000000000000: 00000002 00000000 00010000 0001 01 123 /run/test.sock\n"
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_LISTENER_INODE_UNPROVEN"):
            OWNER._require_unique_unix_listener(header, "/run/test.sock")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_LISTENER_INODE_UNPROVEN"):
            OWNER._require_unique_unix_listener(header + good + good, "/run/test.sock")
        bad_state = good.replace(" 0001 01 ", " 0001 02 ")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_ROW_NOT_STREAM_LISTENER"):
            OWNER._require_unique_unix_listener(header + bad_state, "/run/test.sock")
        bad_type = good.replace(" 0001 01 ", " 0002 01 ")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_ROW_NOT_STREAM_LISTENER"):
            OWNER._require_unique_unix_listener(header + bad_type, "/run/test.sock")
        bad_flags = good.replace("00010000", "00000000")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_LISTENER_FLAG_MISSING"):
            OWNER._require_unique_unix_listener(header + bad_flags, "/run/test.sock")
        accepted_peer = good.replace(" 0001 01 ", " 0001 03 ").replace(" 123 /", " 124 /")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_LISTENER_INODE_UNPROVEN"):
            OWNER._require_unique_unix_listener(header + accepted_peer + good,
                                                "/run/test.sock")

    def test_missing_or_changing_peer_socket_fd_holds(self):
        identity = {"pid": 42, "start_ticks": 77}
        listener = {"kernel_inode": 123, "path": "/run/test.sock",
                    "type": "0001", "state": "01"}
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_PEER_SOCKET_FD_UNPROVEN"):
            OWNER._require_stable_peer_listener(identity, identity, [], [],
                                                listener, listener)
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_PEER_SOCKET_FD_UNPROVEN"):
            OWNER._require_stable_peer_listener(identity, identity, ["4"], ["5"],
                                                listener, listener)
        changed = {**listener, "kernel_inode": 124}
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_PEER_SOCKET_FD_UNPROVEN"):
            OWNER._require_stable_peer_listener(identity, identity, ["4"], ["4"],
                                                listener, changed)

    def test_peer_identity_change_is_rejected(self):
        endpoint = self._peer_endpoint_for_validation()
        changed = {**endpoint["daemon"], "start_ticks": 78}

        class CredSocket:
            calls = 0

            def getsockopt(self, *_args):
                return struct.pack("3i", 42, 0, 0)

        with (mock.patch.object(OWNER, "probe_supervisor_daemon_identity",
                                side_effect=[endpoint["daemon"], changed]),
              mock.patch.object(OWNER, "_process_effective_credentials",
                                return_value=(0, 0)),
              mock.patch.object(OWNER, "_read_effective_supervisor_config",
                                return_value=(None, endpoint["config_identity"])),
              mock.patch.object(OWNER, "_unix_socket_snapshot",
                                return_value=endpoint["socket"]),
              mock.patch.object(OWNER, "_unix_socket_peer_linkage",
                                return_value=endpoint["socket_linkage"]),
              mock.patch.object(OWNER.os, "pidfd_open", return_value=123),
              mock.patch.object(OWNER.os, "close")):
            with self.assertRaisesRegex(RuntimeError,
                                        "HOLD_EMERGENCY_STOP_UNIX_RPC_PEER_PROCESS_CHANGED"):
                OWNER._verify_unix_rpc_peer(CredSocket(), endpoint)

    def test_socket_inode_change_is_rejected(self):
        endpoint = self._peer_endpoint_for_validation()

        class CredSocket:
            def getsockopt(self, *_args):
                return struct.pack("3i", 42, 0, 0)

        changed_socket = {**endpoint["socket"], "inode": 124}
        with (mock.patch.object(OWNER, "probe_supervisor_daemon_identity",
                                return_value=endpoint["daemon"]),
              mock.patch.object(OWNER, "_process_effective_credentials",
                                return_value=(0, 0)),
              mock.patch.object(OWNER, "_read_effective_supervisor_config",
                                return_value=(None, endpoint["config_identity"])),
              mock.patch.object(OWNER, "_unix_socket_snapshot",
                                return_value=changed_socket),
              mock.patch.object(OWNER.os, "pidfd_open", return_value=123),
              mock.patch.object(OWNER.os, "close")):
            with self.assertRaisesRegex(RuntimeError,
                                        "HOLD_EMERGENCY_STOP_UNIX_RPC_SOCKET_INODE_CHANGED"):
                OWNER._verify_unix_rpc_peer(CredSocket(), endpoint)

    def test_rpc_probe_rejects_getpid_mismatch(self):
        endpoint = self._peer_endpoint_for_validation()
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_TARGET_PREFLIGHT_MISMATCH"):
            OWNER._validate_unix_rpc_probe(
                endpoint, 99,
                {"statecode": 1, "statename": "RUNNING"},
                {"name": OWNER.SUPERVISOR_SERVICE, "statename": "RUNNING",
                 "pid": OWNER.MODEL_PID})

    def test_lost_uds_reply_dispatches_once_without_retry(self):
        body = xmlrpc.client.dumps((True,), methodresponse=True).encode("utf-8")

        class LostReplySocket:
            send_calls = 0

            def settimeout(self, _seconds):
                pass

            def connect(self, _path):
                pass

            def getsockopt(self, *_args):
                return struct.pack("3i", 42, 0, 0)

            def sendall(self, _request):
                self.send_calls += 1
                raise OSError("reply path uncertain")

            def close(self):
                pass

        fake = LostReplySocket()
        OWNER.STOP_REQUEST_DISPATCHED = False
        OWNER.SUPERVISOR_RPC_STOP_DISPATCHED = False
        with (mock.patch.object(OWNER, "_supervisor_unix_endpoint_snapshot",
                                return_value=self.endpoint),
              mock.patch.object(OWNER, "_verify_unix_rpc_peer"),
              mock.patch.object(OWNER.os, "pidfd_open", return_value=123),
              mock.patch.object(OWNER.os, "close"),
              mock.patch.object(OWNER.socket, "socket", return_value=fake)):
            with self.assertRaisesRegex(RuntimeError,
                                        "HOLD_EMERGENCY_STOP_UNIX_RPC_CALL_FAILED"):
                OWNER._supervisor_unix_rpc(
                    self.endpoint, "supervisor.stopProcess",
                    (OWNER.SUPERVISOR_SERVICE, True))
        self.assertEqual(fake.send_calls, 1)
        self.assertTrue(OWNER.STOP_REQUEST_DISPATCHED)
        self.assertTrue(OWNER.SUPERVISOR_RPC_STOP_DISPATCHED)

    def test_config_parser_defaults_are_rejected(self):
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string("[DEFAULT]\ncommand=/unexpected\n[program:nox]\nfoo=bar\n")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_TEST_DEFAULTS_REJECTED"):
            with mock.patch.object(OWNER, "fail",
                                   side_effect=RuntimeError(
                                       "HOLD_EMERGENCY_STOP_TEST_DEFAULTS_REJECTED")):
                OWNER._reject_config_defaults(parser, "TEST_DEFAULTS_REJECTED")

    def test_known_supervisor_include_section_types_are_accepted(self):
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(
            "[program:nox-ds41-8098]\ncommand=/opt/nox\n"
            "[eventlistener:audit]\ncommand=/opt/audit\nevents=PROCESS_STATE\n"
            "[fcgi-program:fastcgi]\ncommand=/opt/fcgi\nsocket=unix:///run/fcgi.sock\n"
            "[group:workers]\nprograms=worker-a,worker-b\n"
        )
        matches = OWNER._validate_supervisor_include_sections(parser, "known.conf")
        self.assertEqual(matches, [("program", "known.conf")])
        self.assertEqual(OWNER._require_unique_target_stanza(matches), "known.conf")

    def test_unknown_supervisor_include_section_is_rejected(self):
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string("[mystery:token_SECRET_abc123]\ncommand=/opt/unknown\n")
        previous = OWNER.DIAGNOSTICS.get("supervisor_include_section_headers")
        OWNER._record_include_section_headers([
            ("unknown.conf", parser.sections())])
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_INCLUDED_SECTION_UNSUPPORTED"):
            OWNER._validate_supervisor_include_sections(parser, "unknown.conf")
        rendered = str(OWNER.DIAGNOSTICS["supervisor_include_section_headers"])
        self.assertNotIn("token_SECRET_abc123", rendered)
        self.assertNotIn("/opt/unknown", rendered)
        if previous is None:
            OWNER.DIAGNOSTICS.pop("supervisor_include_section_headers", None)
        else:
            OWNER.DIAGNOSTICS["supervisor_include_section_headers"] = previous

    def test_malformed_secret_like_section_header_is_redacted(self):
        secret_header = "program:secret TOKEN=abc123"
        previous = OWNER.DIAGNOSTICS.get("supervisor_include_section_headers")
        try:
            OWNER._record_include_section_headers([
                ("malformed.conf", [secret_header])])
            rendered = str(OWNER.DIAGNOSTICS["supervisor_include_section_headers"])
            self.assertNotIn(secret_header, rendered)
            self.assertIn("'unknown': True", rendered)
            self.assertIn("'unknown_section_count': 1", rendered)
        finally:
            if previous is None:
                OWNER.DIAGNOSTICS.pop("supervisor_include_section_headers", None)
            else:
                OWNER.DIAGNOSTICS["supervisor_include_section_headers"] = previous

    def test_include_section_diagnostic_is_sorted_and_omits_values(self):
        previous = OWNER.DIAGNOSTICS.get("supervisor_include_section_headers")
        try:
            OWNER._record_include_section_headers([
                ("z.conf", ["program:z", "mystery:hidden"]),
                ("a.conf", ["eventlistener:a"]),
            ])
            record = OWNER.DIAGNOSTICS["supervisor_include_section_headers"]
            self.assertEqual([row["basename"] for row in record["files"]],
                             ["a.conf", "z.conf"])
            self.assertEqual(record["files"][1]["section_headers"], ["program:z"])
            self.assertTrue(record["files"][1]["unknown"])
            self.assertEqual(record["files"][1]["unknown_section_count"], 1)
            self.assertFalse(record["values_included"])
            self.assertNotIn("mystery:hidden", str(record))
            self.assertNotIn("/opt/unknown", str(record))
        finally:
            if previous is None:
                OWNER.DIAGNOSTICS.pop("supervisor_include_section_headers", None)
            else:
                OWNER.DIAGNOSTICS["supervisor_include_section_headers"] = previous

    def test_duplicate_target_sections_across_include_files_hold(self):
        target = "nox-ds41-8098"
        matches = [("program", "a.conf"), ("program", "b.conf")]
        self.assertEqual(target, OWNER.SUPERVISOR_SERVICE)
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_TARGET_STANZA_NOT_UNIQUE"):
            OWNER._require_unique_target_stanza(matches)

    def test_target_name_collision_with_other_known_section_type_holds(self):
        matches = [("eventlistener", "audit.conf")]
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_UNIX_RPC_TARGET_STANZA_NOT_UNIQUE"):
            OWNER._require_unique_target_stanza(matches)

    def test_holder_second_stage_is_not_available(self):
        self.assertFalse(hasattr(OWNER, "stop_holder_only_if_model_stop_is_insufficient"))
        self.assertFalse(hasattr(OWNER, "signal"))


if __name__ == "__main__":
    unittest.main()
