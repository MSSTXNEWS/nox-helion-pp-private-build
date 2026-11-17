"""Synthetic TempFS only: no actual /proc, credentials, network or NOX calls."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_model_identity_readback as m
import model_identity_audit_entry as entry


class ModelIdentityReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'nox'
        self.proc = Path(self.temp.name)/'proc'
        self.pid = self.proc/str(m.PINNED_PID)
        for path in (self.root/'scripts', self.root/'status', self.root/'config', self.root/'state',
                     self.pid/'ns', self.pid/'net', self.pid/'fd', self.proc/'self/ns'):
            path.mkdir(parents=True, exist_ok=True)
        source_pins = {}
        for name in m.projection.SOURCE_PINS:
            raw = ('# SYNTHETIC_SOURCE_' + name + '\n').encode()
            (self.root/'scripts'/name).write_bytes(raw)
            source_pins[name] = m.sha(raw)
        self.model = '/root/nox/models/Synthetic-Model-Q4.gguf'
        (self.root/'status/status.json').write_text(json.dumps({'model': self.model,
            'password': 'STATUS_PRIVATE_FIELD_MUST_NOT_EXPORT'}))
        (self.root/'config/backend.json').write_text(json.dumps({'host': '127.0.0.1', 'port': 8098,
            'model': self.model, 'api_key': 'CONFIG_PRIVATE_FIELD_MUST_NOT_EXPORT'}))
        args = ['/opt/reviewed/llama-server', '--model', self.model, '--api-key',
                'ARGV_PRIVATE_VALUE_MUST_NOT_EXPORT', '--host', '0.0.0.0', '--port', '8098']
        raw = ('\0'.join(args)+'\0').encode()
        (self.pid/'cmdline').write_bytes(raw)
        (self.pid/'stat').write_text(f'{m.PINNED_PID} (synthetic) S 114 '+'0 '*17+'172046662 0\n')
        (self.pid/'status').write_text('Uid:\t'+'\t'.join([str(os.getuid())]*4)+'\n')
        (self.pid/'exe').symlink_to('/opt/reviewed/llama-server')
        (self.pid/'cwd').symlink_to('/root/nox')
        (self.pid/'ns/net').symlink_to('net:[4026531993]')
        (self.proc/'self/ns/net').symlink_to('net:[4026531993]')
        (self.pid/'fd/17').symlink_to('socket:[7001]')
        (self.pid/'fd/18').symlink_to('/private/descriptor/target-not-exported')
        self.tcp = ('  sl  local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n'
                    f'0: 00000000:1FA2 00000000:0000 0A 00000000:00000000 00:00000000 00000000 {os.getuid()} 0 7001 1 0\n')
        (self.pid/'net/tcp').write_text(self.tcp)
        lockpath = self.root/'state/owner_maintenance.lock'
        lockpath.write_bytes(b'')
        lockpath.chmod(0o600)
        self.lockfd = os.open(lockpath, os.O_RDONLY)
        self.addCleanup(os.close, self.lockfd)
        info = os.fstat(self.lockfd)
        process_pin = {**m.PROCESS_PIN, 'argv_sha256': m.sha(raw),
                       'exe_path_sha256': m.sha(b'/opt/reviewed/llama-server'),
                       'cwd_sha256': m.sha(b'/root/nox')}
        for target, name, value in ((m, 'ROOT', self.root), (m, 'PROC', self.proc),
                (m, 'OWNER_UID', os.getuid()), (m, 'PROCESS_PIN', process_pin),
                (m, 'LOCK_PIN', {'dev': info.st_dev, 'ino': info.st_ino}),
                (m.projection, 'SOURCE_PINS', source_pins)):
            context = patch.object(target, name, value)
            context.start(); self.addCleanup(context.stop)
        self.http_calls = []
        outer = self
        class Response:
            status = 200
            def read(self, bound):
                assert bound == 65537
                return b'{"status":"ok","ignored":"HEALTH_PRIVATE_FIELD"}'
            def getheader(self, name, default):
                assert name == 'Content-Encoding'
                return default
        class Connection:
            def __init__(self, host, port, *, timeout):
                outer.assertEqual((host, port), ('127.0.0.1', 8098))
                outer.assertLessEqual(timeout, .8)
            def request(self, method, path, *, headers):
                outer.http_calls.append((method, path, headers))
            def getresponse(self):
                return Response()
            def close(self):
                pass
        context = patch.object(m.http.client, 'HTTPConnection', Connection)
        context.start(); self.addCleanup(context.stop)

    def observe(self):
        return m.observe('6962437325', 'a'*40, maintenance_lock_fd=self.lockfd)

    def test_current_listener_binding_safe_model_reference_and_single_health_get(self):
        result = self.observe()
        self.assertEqual(result['status'], 'BOUNDED_LISTENER_MODEL_REFERENCE_SNAPSHOT', result)
        self.assertIs(result['listener_model_reference_verified'], True)
        self.assertIs(result['argv_projection']['listener_process_binding_verified'], True)
        self.assertEqual(result['argv_projection']['model_argument']['model_basename'], 'Synthetic-Model-Q4.gguf')
        self.assertEqual(result['listener']['socket_inode'], 7001)
        self.assertEqual(result['listener']['file_descriptors'], [17])
        self.assertEqual(result['listener']['pid'], 3266857)
        self.assertEqual(result['listener']['start_ticks'], 172046662)
        self.assertEqual(len(self.http_calls), 1)
        self.assertEqual(self.http_calls[0][:2], ('GET', '/health'))
        self.assertIs(result['configured_primary_healthy_by_source_rule'], True)
        self.assertIs(result['last_chat_backend_identified'], False)
        self.assertIs(result['weight_content_identity_verified'], False)
        public = json.dumps(result)
        for hidden in ('ARGV_PRIVATE_VALUE', 'STATUS_PRIVATE_FIELD', 'CONFIG_PRIVATE_FIELD',
                       'HEALTH_PRIVATE_FIELD', '/private/descriptor/', 'SYNTHETIC_SOURCE_'):
            self.assertNotIn(hidden, public)
        self.assertIn('previous_audit_sensitive_marker', public)

    def test_wrong_socket_owner_or_namespace_blocks_health_and_identity(self):
        target = self.pid/'fd/17'
        target.unlink(); target.symlink_to('socket:[7002]')
        result = self.observe()
        self.assertEqual(result['status'], 'HOLD_IDENTITY_SOCKET_NOT_OWNED')
        self.assertEqual(self.http_calls, [])
        self.assertIs(result['listener_model_reference_verified'], False)
        target.unlink(); target.symlink_to('socket:[7001]')
        ns = self.pid/'ns/net'; ns.unlink(); ns.symlink_to('net:[4026531994]')
        result = self.observe()
        self.assertEqual(result['status'], 'HOLD_IDENTITY_NETWORK_NAMESPACE')
        self.assertEqual(self.http_calls, [])

    def test_duplicate_listener_or_changed_source_fail_before_network(self):
        target = self.pid/'net/tcp'
        target.write_text(self.tcp + self.tcp.splitlines(True)[1].replace('7001', '7003'))
        result = self.observe()
        self.assertEqual(result['status'], 'HOLD_IDENTITY_LISTENER_NOT_UNIQUE')
        self.assertEqual(self.http_calls, [])
        target.write_text(self.tcp)
        (self.root/'scripts/common.py').write_text('# not the reviewed source\n')
        result = self.observe()
        self.assertEqual(result['status'], 'HOLD_IDENTITY_SOURCE_SHA:common.py')
        self.assertEqual(self.http_calls, [])

    def test_configured_route_is_not_replaced_with_guessed_pid_or_host(self):
        target = self.root/'config/backend.json'
        for value, expected in (({'host':'localhost', 'port':8098}, 'HOLD_IDENTITY_LOCALHOST_RESOLUTION_NOT_OBSERVED'),
                                ({'host':'127.0.0.1', 'port':8085}, 'HOLD_IDENTITY_CONFIGURED_PORT_NOT_PINNED_LISTENER'),
                                ({'host':'external.invalid', 'port':8098}, 'HOLD_BACKEND_NON_LOOPBACK_HOST')):
            with self.subTest(config=value):
                target.write_text(json.dumps(value))
                result = self.observe()
                self.assertEqual(result['status'], expected)
                self.assertEqual(self.http_calls, [])
                self.assertIs(result['listener_model_reference_verified'], False)

    def test_entry_reuses_existing_lock_and_emits_bounded_public_receipt(self):
        sink = io.StringIO()
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '6962437325',
                                    'NOX_OWNER_SOURCE_SHA': 'a'*40}), contextlib.redirect_stdout(sink):
            status = entry.main()
        self.assertEqual(status, 0)
        lines = sink.getvalue().splitlines()
        self.assertEqual(lines[-1], 'NOX_MAINT_AUDIT_COMPLETE=true')
        envelope = json.loads(lines[0].removeprefix('NOX_MAINT_AUDIT='))
        self.assertEqual(envelope['kind'], 'model_identity_readback')
        result = envelope['data']
        self.assertEqual(result['owner_request'], '6962437325')
        self.assertEqual(result['owner_context_environment_reads'], 2)
        self.assertIs(result['listener_model_reference_verified'], True)
        self.assertEqual(len(self.http_calls), 1)
        self.assertLess(len(lines[0].encode()), 32768)
        self.assertEqual(entry.signal.getitimer(entry.signal.ITIMER_REAL), (0.0, 0.0))


if __name__ == '__main__':
    unittest.main()
