"""Mocked public I/O and real tiny memfd checks; no network, model or GPU."""
import ast
from contextlib import ExitStack
import errno
import hashlib
import io
import json
import re
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE / 'qwen_student_training_entry_transport_candidate.py'
ORIGINAL = HERE / 'qwen_student_training_entry_revision.py'
BASE_SHA = '530b59ee1723c5d6279dd8523d3f090c07e984561103d567b2de2b552d1108a9'
DEPENDENCIES = {
    'owner_qwen_training_contract': (Path('/tmp/nox_qwen_owner_qwen_training_contract.py'),
        '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a'),
    'owner_qwen_memfd': (Path('/tmp/nox_qwen_owner_qwen_memfd.py'),
        '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82'),
}
with patch.dict(sys.modules):
    for name, (path, pin) in DEPENDENCIES.items():
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin:
            raise RuntimeError('Pinned fixture dependency changed')
        module = types.ModuleType(name); module.__file__ = str(path)
        sys.modules[name] = module
        exec(compile(raw, str(path), 'exec'), module.__dict__)
    S = types.ModuleType('_public_transport_candidate_fixture'); S.__file__ = str(CANDIDATE)
    exec(compile(CANDIDATE.read_bytes(), str(CANDIDATE), 'exec'), S.__dict__)


def row(data=b'abcdefgh', name='fixture.safetensors'):
    return {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'immutable_url': 'https://huggingface.co/public-test/' + name}


class FakeSocket:
    def __init__(self): self.timeouts = []
    def settimeout(self, value): self.timeouts.append(value)


class Response:
    def __init__(self, items, *, total=8, offset=0, status=None, callback=None):
        self.items = list(items); self.status = status if status is not None else (206 if offset else 200)
        self.headers = {'Content-Length': str(total - offset)}
        if offset: self.headers['Content-Range'] = f'bytes {offset}-{total-1}/{total}'
        self.sock = FakeSocket(); self.fp = types.SimpleNamespace(raw=types.SimpleNamespace(_sock=self.sock))
        self.closed = False; self.read_calls = 0; self.callback = callback
    def geturl(self): return 'https://cdn-lfs.hf.co/public-fixture'
    def read1(self, count):
        self.read_calls += 1
        if self.callback:
            callback, self.callback = self.callback, None; callback()
        if not self.items: return b''
        value = self.items.pop(0)
        if isinstance(value, BaseException): raise value
        if isinstance(value, bytes) and len(value) > count:
            self.items.insert(0, value[count:]); value = value[:count]
        return value
    def close(self): self.closed = True; self.fp = None


class Opener:
    def __init__(self, answers): self.answers = list(answers); self.requests = []; self.lock = threading.Lock()
    def open(self, request, timeout):
        with self.lock:
            self.requests.append((request, timeout))
            value = self.answers.pop(0)
        if isinstance(value, BaseException): raise value
        return value


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.parent = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.events = []; self.guard_calls = []
        self.registry = self.stack.enter_context(S.PublicTransportRevision(self.parent,
            guard=lambda additional: self.guard_calls.append(additional), streams=1, progress=self.events.append))
        self.stack.enter_context(patch.object(self.registry, '_backoff', side_effect=lambda _: self.registry._budget()))
    def opener(self, answers):
        value = Opener(answers)
        self.stack.enter_context(patch.object(S._public_memfd_base.urllib.request, 'build_opener', return_value=value))
        return value
    def assert_saved(self, expected=b'abcdefgh'):
        path = self.registry.directory / 'fixture.safetensors'
        self.assertTrue(self.registry.verify_path(path, hashlib.sha256(expected).hexdigest(), len(expected)))
        fd = self.registry._owned[path.name]
        self.assertEqual(S.os.pread(fd, len(expected) + 1, 0), expected)
        with self.assertRaises(OSError): S.os.write(fd, b'x')

    def test_normal_transfer_real_seals_and_actual_source_identity(self):
        response = Response([b'ab', b'cdef', b'gh']); opener = self.opener([response])
        result = self.registry.stage([row()]); self.assert_saved()
        self.assertTrue(response.closed); self.assertEqual(len(opener.requests), 1)
        self.assertEqual(result['transport']['runtime_entry_sha256'], hashlib.sha256(CANDIDATE.read_bytes()).hexdigest())
        self.assertEqual(result['transport']['base_helper_sha256'], DEPENDENCIES['owner_qwen_memfd'][1])
        self.assertTrue(all(0 < value <= 30 for value in response.sock.timeouts))
        self.assertIn(8, self.guard_calls)
        self.assertEqual(self.events[-1]['bytes'], 8); self.assertEqual(self.events[-1]['total'], 8)

    def test_successful_partial_writes_commit_every_reported_byte(self):
        self.opener([Response([b'abcdefgh'])]); actual = S.os.write; writes = []
        def partial(fd, data):
            count = actual(fd, data[:2]); writes.append(count); return count
        with patch.object(S.os, 'write', side_effect=partial): self.registry.stage([row()])
        self.assertEqual(writes, [2, 2, 2, 2]); self.assert_saved()

    def test_read_timeout_resumes_at_committed_offset(self):
        first = Response([b'abc', TimeoutError('private URL token NOT_EXPORTED')])
        second = Response([b'defgh'], offset=3)
        opener = self.opener([first, second]); self.registry.stage([row()]); self.assert_saved()
        self.assertEqual(opener.requests[1][0].get_header('Range'), 'bytes=3-')
        event = next(e for e in self.events if e.get('stage') == 'READ')
        self.assertEqual(event['committed_offset'], 3); self.assertEqual(event['attempt'], 1)
        self.assertEqual(event['exception_type'], 'TimeoutError'); self.assertIsInstance(event['io_elapsed_seconds'], float)
        self.assertTrue(first.closed and second.closed)
        self.assertNotIn('NOT_EXPORTED', str(self.events)); self.assertNotIn('https:', str(self.events))

    def test_open_transient_dns_retry_and_safe_negative_errno(self):
        opener = self.opener([urllib.error.URLError(socket.gaierror(socket.EAI_AGAIN, 'NOT_EXPORTED')), Response([b'abcdefgh'])])
        self.registry.stage([row()]); self.assert_saved(); self.assertEqual(len(opener.requests), 2)
        failure = next(e for e in self.events if e.get('exception_type') == 'URLError')
        self.assertEqual(failure['errno'], socket.EAI_AGAIN)

    def test_http403_is_not_retried_or_body_exported(self):
        body = io.BytesIO(b'NOT_EXPORTED'); error = urllib.error.HTTPError(
            'https://huggingface.co/?signed=NOT_EXPORTED', 403, 'NOT_EXPORTED', {}, body)
        opener = self.opener([error])
        with self.assertRaisesRegex(S.Hold, 'TRANSPORT_OPEN_FAILED'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1); self.assertTrue(body.closed)
        failure = next(e for e in self.events if e.get('exception_type') == 'HTTPError')
        self.assertEqual(failure['http_status'], 403); self.assertNotIn('NOT_EXPORTED', str(self.events))

    def test_network_retry_budget_is_finite(self):
        opener = self.opener([TimeoutError('NOT_EXPORTED') for _ in range(self.registry.MAX_ATTEMPTS)])
        with self.assertRaisesRegex(S.Hold, 'TRANSPORT_OPEN_FAILED'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 6)
        self.assertEqual([e['attempt'] for e in self.events if e.get('exception_type')], list(range(1, 7)))

    def test_partial_write_failure_is_terminal_and_reports_committed_offset(self):
        opener = self.opener([Response([b'abcdefgh'])]); actual = S.os.write; calls = []
        def partial_then_fail(fd, data):
            calls.append(len(data))
            if len(calls) == 1: return actual(fd, data[:2])
            raise OSError(errno.ENOSPC, 'NOT_EXPORTED')
        with patch.object(S.os, 'write', side_effect=partial_then_fail):
            with self.assertRaisesRegex(S.Hold, 'TRANSPORT_WRITE_FAILED'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1)
        fd = self.registry._owned['fixture.safetensors']; self.assertEqual(S.os.fstat(fd).st_size, 2)
        self.assertEqual(S.os.lseek(fd, 0, S.os.SEEK_CUR), 2)
        failure = next(e for e in self.events if e.get('stage') == 'WRITE')
        self.assertEqual(failure['committed_offset'], 2); self.assertEqual(failure['errno'], errno.ENOSPC)
        self.assertEqual(self.registry.verified, {}); self.assertNotIn('NOT_EXPORTED', str(self.events))

    def test_write_zero_is_terminal(self):
        opener = self.opener([Response([b'abcdefgh'])])
        with patch.object(S.os, 'write', return_value=0):
            with self.assertRaisesRegex(S.Hold, 'TRANSPORT_WRITE_COUNT'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1); self.assertEqual(self.registry.verified, {})

    def test_sha_mismatch_does_not_publish_link(self):
        self.opener([Response([b'xxxxxxxx'])])
        with self.assertRaisesRegex(S.Hold, 'HOLD_MEMFD_WEIGHT_SHA'): self.registry.stage([row()])
        self.assertEqual(self.registry.verified, {}); self.assertEqual(list(self.registry.directory.iterdir()), [])

    def test_resumed_wrong_range_is_not_retried(self):
        bad = Response([b'defgh'], offset=3); bad.headers['Content-Range'] = 'bytes 2-7/8'
        opener = self.opener([Response([b'abc', TimeoutError()]), bad])
        with self.assertRaisesRegex(S.Hold, 'HOLD_MEMFD_RANGE_RESPONSE'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 2); self.assertEqual(self.registry.verified, {})

    def test_length_encoding_and_redirect_fail_closed(self):
        cases = [('Content-Length', '7', 'CONTENT_LENGTH'), ('Transfer-Encoding', 'chunked', 'RESPONSE_ENCODING'),
                 ('Content-Encoding', 'gzip', 'RESPONSE_ENCODING')]
        for key, value, code in cases:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory(dir=self.parent) as tmp:
                    with S.PublicTransportRevision(Path(tmp), guard=lambda _: None, streams=1) as registry:
                        response = Response([b'abcdefgh']); response.headers[key] = value
                        with patch.object(S._public_memfd_base.urllib.request, 'build_opener', return_value=Opener([response])):
                            with self.assertRaisesRegex(S.Hold, code): registry.stage([row()])
        bad = Response([b'abcdefgh']); bad.geturl = lambda: 'https://private.invalid/?secret=NOT_EXPORTED'
        opener = self.opener([bad])
        with self.assertRaisesRegex(S.Hold, 'UNREVIEWED_PUBLIC_WEIGHT_REDIRECT'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1)

    def test_stop_during_read_before_write_propagates_without_retry(self):
        stopped = [False]
        def guard(_):
            if stopped[0]: raise S.Hold('HOLD_TRAINING_STOP_REQUESTED')
        self.registry.guard = guard
        response = Response([b'abcdefgh'], callback=lambda: stopped.__setitem__(0, True))
        opener = self.opener([response])
        with self.assertRaisesRegex(S.Hold, 'HOLD_TRAINING_STOP_REQUESTED'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(S.os.fstat(self.registry._owned['fixture.safetensors']).st_size, 0)

    def test_guard_oserror_is_not_a_network_retry(self):
        stopped = [False]
        def guard(_):
            if stopped[0]: raise OSError(errno.EAGAIN, 'private-resource-diagnostic')
        self.registry.guard = guard
        opener = self.opener([Response([b'abcdefgh'], callback=lambda: stopped.__setitem__(0, True))])
        with self.assertRaises(OSError): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1)
        self.assertFalse(any(e.get('exception_type') == 'BlockingIOError' for e in self.events))

    def test_global_deadline_during_read_prevents_write_or_retry(self):
        response = Response([b'abcdefgh'], callback=lambda: setattr(self.registry, '_transport_deadline', time.monotonic() - 1))
        opener = self.opener([response])
        with self.assertRaisesRegex(S.Hold, 'TRANSPORT_DEADLINE'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(S.os.fstat(self.registry._owned['fixture.safetensors']).st_size, 0)

    def test_read_timeout_shrinks_to_remaining_deadline(self):
        self.registry._transport_deadline = time.monotonic() + .5
        response = Response([b'a'])
        self.assertEqual(self.registry._read1(response, 1), b'a')
        self.assertTrue(0 < response.sock.timeouts[0] <= .5)

    def test_eof_timeout_is_not_retried_at_invalid_end_offset(self):
        opener = self.opener([Response([b'abcdefgh', TimeoutError()])])
        with self.assertRaisesRegex(S.Hold, 'DOWNLOAD_TERMINATION_UNVERIFIED'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1); self.assertEqual(self.registry.verified, {})

    def test_read1_required_no_read_fallback(self):
        response = Response([b'abcdefgh']); response.read1 = None
        opener = self.opener([response])
        with self.assertRaisesRegex(S.Hold, 'SINGLE_READ_REQUIRED'): self.registry.stage([row()])
        self.assertEqual(len(opener.requests), 1)

    def test_four_parallel_workers_and_original_cleanup(self):
        barrier = threading.Barrier(4); lock = threading.Lock(); active = [0, 0]
        def overlap():
            with lock: active[0] += 1; active[1] = max(active)
            barrier.wait(timeout=3)
            with lock: active[0] -= 1
        records = [row(name=f'public-{i}.safetensors') for i in range(4)]
        answers = [Response([b'abcdefgh'], callback=overlap) for _ in records]
        opener = self.opener(answers)
        with tempfile.TemporaryDirectory(dir=self.parent) as tmp:
            with S.PublicTransportRevision(Path(tmp), guard=lambda _: None, streams=4) as registry:
                result = registry.stage(records); directory = registry.directory; descriptors = list(registry._owned.values())
                self.assertEqual(result['files'], 4); self.assertEqual(active[1], 4)
            self.assertFalse(directory.exists())
            for fd in descriptors:
                with self.assertRaises(OSError): S.os.fstat(fd)
        self.assertEqual(len(opener.requests), 4)
        with self.assertRaisesRegex(S.Hold, 'STAGING_CONTRACT'):
            S.PublicTransportRevision(self.parent, guard=lambda _: None, streams=5)


class SourceAndPolicyTests(unittest.TestCase):
    def test_exact_inverse_to_frozen530_and_inherited_lifecycle(self):
        original = ORIGINAL.read_bytes(); self.assertEqual(hashlib.sha256(original).hexdigest(), BASE_SHA)
        source = CANDIDATE.read_text(); tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PublicTransportRevision')
        lines = source.splitlines(keepends=True)
        candidate = ''.join(lines[:node.lineno-1] + lines[node.end_lineno:])
        candidate = candidate.replace('import owner_qwen_memfd as _public_memfd_base\n', '', 1)
        candidate = candidate.replace('registry = resources.enter_context(PublicTransportRevision(',
                                      'registry = resources.enter_context(SealedModel(', 1)
        self.assertEqual(ast.dump(ast.parse(candidate), include_attributes=False),
                         ast.dump(ast.parse(original), include_attributes=False))
        start = source.index('class PublicTransportRevision(SealedModel):')
        end = source.index('def read_json(', start)
        inverse = (source[:start] + source[end:]).replace('import owner_qwen_memfd as _public_memfd_base\n', '', 1)
        inverse = inverse.replace('registry = resources.enter_context(PublicTransportRevision(',
                                  'registry = resources.enter_context(SealedModel(', 1)
        self.assertEqual(hashlib.sha256(inverse.encode()).hexdigest(), BASE_SHA)
        for name in ('__init__', '_check', 'verify_path', 'close', '__enter__', '__exit__'):
            self.assertIs(getattr(S.PublicTransportRevision, name), getattr(S.SealedModel, name))
        self.assertLessEqual(S.PublicTransportRevision.STAGING_SECONDS, 1200)

    def test_existing_sanitizer_still_sees_checked_byte_counts(self):
        path = Path('/tmp/nox_qwen_window_entry_4d5.py'); raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7')
        function = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'safe_log_summary')
        namespace = {'re': re, 'json': json}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<pinned-safe-log-summary>', 'exec'), namespace)
        event = {'state': 'PINNED_PUBLIC_BASE_STAGING', 'stage': 'WRITE', 'bytes': 2, 'total': 8,
                 'errno': 28, 'exception_type': 'OSError', 'file': 'public-only'}
        summary = namespace['safe_log_summary'](json.dumps(event).encode())
        self.assertEqual(summary['safe_events'], [{'state': 'PINNED_PUBLIC_BASE_STAGING',
                         'public_file_bytes': 2, 'public_file_total_bytes': 8}])
        self.assertFalse(summary['raw_text_exported'])

    def test_actual_candidate_hash_is_execution_binding_not_origin_transport(self):
        shared_path = HERE / 'owner_qwen_execution_revision.py'; raw = shared_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), S.EXECUTION_MODULE_SHA)
        shared = types.ModuleType('_transport_binding_fixture'); shared.__file__ = str(shared_path)
        exec(compile(raw, str(shared_path), 'exec'), shared.__dict__)
        current_sha = hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()
        origin = {'entry_sha256': shared.ORIGIN['previous_entry_sha256'],
                  'contract_sha256': shared.ORIGINAL_SOURCES['owner_qwen_training_contract.py'],
                  'memfd_source_sha256': S.PublicTransportRevision.BASE_HELPER_SHA, 'scientific_fixture': 25}
        ctx = {'lineage': origin, 'execution': {'runtime_entry_sha256': current_sha, 'reference': {'fixture': 'source-only'},
            'descriptor_sha256': 'a'*64, 'admission_sha256': 'b'*64, 'verifier_sha256': S.EXECUTION_MODULE_SHA}}
        recomputed = {**origin, 'entry_sha256': current_sha}
        self.assertEqual(shared.resolve_origin_lineage(recomputed, ctx), origin)
        self.assertEqual(shared.execution_binding(ctx)['runtime_entry_sha256'], current_sha)
        self.assertEqual(origin['entry_sha256'], shared.ORIGIN['previous_entry_sha256'])
        with self.assertRaises(Exception): shared.resolve_origin_lineage({**recomputed, 'entry_sha256': BASE_SHA}, ctx)
        with self.assertRaises(Exception): shared.resolve_origin_lineage({**recomputed, 'scientific_fixture': 26}, ctx)

    def test_backoff_is_stop_aware_and_finite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with S.PublicTransportRevision(Path(tmp), guard=lambda _: None, streams=1) as registry:
                clock = [10.0]
                class Abort:
                    def is_set(self): return False
                    def set(self): pass
                    def wait(self, duration): clock[0] += duration
                registry._abort = Abort(); registry._transport_started = 10; registry._transport_deadline = 100
                with patch.object(S.time, 'monotonic', side_effect=lambda: clock[0]): registry._backoff(1)
                self.assertGreaterEqual(clock[0], 10.5); self.assertLess(clock[0], 10.7)
                registry._transport_deadline = 10.6
                with patch.object(S.time, 'monotonic', side_effect=lambda: clock[0]):
                    with self.assertRaisesRegex(S.Hold, 'TRANSPORT_DEADLINE'): registry._backoff(6)


if __name__ == '__main__': unittest.main()
