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
              mock.patch.object(OWNER.socket, "socket", return_value=fake)):
            value = OWNER._supervisor_unix_rpc(self.endpoint, "supervisor.getPID", ())
        self.assertEqual(value, 42)
        self.assertIn(b"POST /RPC2 HTTP/1.0", fake.request)
        self.assertFalse(OWNER.SUPERVISOR_RPC_STOP_DISPATCHED)

    def test_config_parser_defaults_are_rejected(self):
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string("[DEFAULT]\ncommand=/unexpected\n[program:nox]\nfoo=bar\n")
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_EMERGENCY_STOP_TEST_DEFAULTS_REJECTED"):
            with mock.patch.object(OWNER, "fail",
                                   side_effect=RuntimeError(
                                       "HOLD_EMERGENCY_STOP_TEST_DEFAULTS_REJECTED")):
                OWNER._reject_config_defaults(parser, "TEST_DEFAULTS_REJECTED")

    def test_holder_second_stage_is_not_available(self):
        self.assertFalse(hasattr(OWNER, "stop_holder_only_if_model_stop_is_insufficient"))
        self.assertFalse(hasattr(OWNER, "signal"))


if __name__ == "__main__":
    unittest.main()
