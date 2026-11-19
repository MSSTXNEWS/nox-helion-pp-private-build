"""Only synthetic responses, a tiny owned memfd and an owned deadline child."""
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import time
import types
import unittest
from unittest import mock
import urllib.error
import urllib.request

PATH = Path(__file__).with_name('owner_qwen_transport_probe.py')
SPEC = importlib.util.spec_from_file_location('transport_probe', PATH)
P = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(P)


class Response:
    def __init__(self, raw, size, code=200, content_range=None):
        self.raw = io.BytesIO(raw); self.code = code; self.closed = False; self.reads = []
        self.headers = {'Content-Length': str(size), 'X-Private': 'DO_NOT_EXPORT'}
        if content_range:
            self.headers['Content-Range'] = content_range
    def geturl(self): return 'https://cdn-lfs.hf.co/public?token=DO_NOT_EXPORT'
    def read(self, count): self.reads.append(count); return self.raw.read(count)
    def close(self): self.closed = True


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.ns = {'__name__': 'synthetic_child'}; exec(compile(P.CHILD, '<child>', 'exec'), self.ns)
        self.policy = {'PublicHFRedirect': urllib.request.HTTPRedirectHandler,
                       'allowed_public_url': lambda value: None}
        self.row = {'immutable_url': 'https://huggingface.co/public', 'bytes': 4 * P.MIB,
                    'sha256': hashlib.sha256(b'metadata').hexdigest()}

    def call(self, response, **kwargs):
        opened = []
        def open_request(request, timeout):
            opened.append(request); self.assertEqual(timeout, 15)
            if isinstance(response, Exception): raise response
            return response
        stream = io.StringIO()
        with mock.patch.object(urllib.request, 'build_opener', return_value=types.SimpleNamespace(open=open_request)) as builder, \
             contextlib.redirect_stdout(stream):
            result = self.ns['request'](self.policy, self.row, 'case', 'synthetic', **kwargs)
        self.assertEqual(len(builder.call_args.args), 1)
        self.assertNotIn('DO_NOT_EXPORT', stream.getvalue())
        return result, opened

    def test_initial_get_has_no_range_and_reads_only_one_mib(self):
        response = Response(b'x' * P.MIB, self.row['bytes'])
        result, calls = self.call(response)
        self.assertTrue(result['ok']); self.assertEqual(calls[0].get_method(), 'GET')
        self.assertIsNone(calls[0].get_header('Range'))
        self.assertEqual(response.reads, [P.MIB]); self.assertTrue(response.closed)
        self.assertFalse(result['full_file_sha_verified'])

    def test_resume_uses_original_open_ended_range(self):
        offset = 3 * 1024 ** 3; self.row['bytes'] = 5368717440
        response = Response(b'x' * P.MIB, self.row['bytes'] - offset, 206,
                            f"bytes {offset}-{self.row['bytes']-1}/{self.row['bytes']}")
        result, calls = self.call(response, offset=offset)
        self.assertTrue(result['ok']); self.assertEqual(calls[0].get_header('Range'), f'bytes={offset}-')
        self.assertEqual(result['bytes_returned'], P.MIB); self.assertFalse(result['full_file_sha_verified'])

    def test_wrong_range_is_rejected_before_read(self):
        response = Response(b'x', self.row['bytes'], 206, 'bytes 0-10/11')
        result, _ = self.call(response, offset=1)
        self.assertFalse(result['ok']); self.assertEqual(result['failure_stage'], 'HEADERS')
        self.assertEqual(result['validation_code'], 'RANGE_RESPONSE'); self.assertEqual(response.reads, [])

    def test_small_metadata_requires_exact_sha_and_eof(self):
        self.row['bytes'] = len(b'metadata')
        response = Response(b'metadata', self.row['bytes'])
        result, _ = self.call(response, full=True)
        self.assertTrue(result['ok']); self.assertTrue(result['full_file_sha_verified'])
        self.assertEqual(response.reads, [len(b'metadata'), 1])
        response = Response(b'METADATA', self.row['bytes'])
        result, _ = self.call(response, full=True)
        self.assertFalse(result['ok']); self.assertEqual(result['validation_code'], 'METADATA_SHA')

    def test_http_error_and_read_error_preserve_numeric_phase_only(self):
        response = urllib.error.HTTPError(self.row['immutable_url'], 403, 'DO_NOT_EXPORT', {}, io.BytesIO())
        result, _ = self.call(response)
        self.assertEqual((result['http_status'], result['failure_stage'], result['exception_type']), (403, 'OPEN', 'HTTPError'))
        response = Response(b'', self.row['bytes'])
        response.read = mock.Mock(side_effect=OSError(104, 'DO_NOT_EXPORT'))
        result, _ = self.call(response)
        self.assertEqual((result['errno'], result['failure_stage'], result['bytes_returned']), (104, 'READ', 0))

    def test_body_budget_applies_before_read(self):
        self.ns['RESERVED'] = 12 * P.MIB
        response = Response(b'x', 1)
        with self.assertRaisesRegex(self.ns['Hold'], 'BODY_BUDGET'):
            self.ns['limited_read'](response, 1)
        self.assertEqual(response.reads, [])

    def test_tiny_memfd_real_write_readback_seal_closes_all_pages(self):
        def seal(fd):
            fcntl.fcntl(fd, getattr(fcntl, 'F_ADD_SEALS', 1033), 15)
            self.assertEqual(fcntl.fcntl(fd, getattr(fcntl, 'F_GET_SEALS', 1034)) & 15, 15)
        captured = []; original = os.memfd_create
        def create(*args):
            fd = original(*args); captured.append(fd); return fd
        with mock.patch.object(os, 'memfd_create', side_effect=create), contextlib.redirect_stdout(io.StringIO()):
            row = self.ns['tiny_memfd']({'seal': seal})
        self.assertTrue(row['ok']); self.assertFalse(row['pages_retained'])
        with self.assertRaises(OSError): os.fstat(captured[0])

    def test_partial_memfd_write_error_is_write_phase_and_closes(self):
        captured = []; original_create = os.memfd_create; original_write = os.write; writes = []
        def create(*args):
            fd = original_create(*args); captured.append(fd); return fd
        def write(fd, value):
            if writes: raise OSError(28, 'DO_NOT_EXPORT')
            writes.append(1); return original_write(fd, value[:17])
        stream = io.StringIO()
        with mock.patch.object(os, 'memfd_create', side_effect=create), mock.patch.object(os, 'write', side_effect=write), \
             contextlib.redirect_stdout(stream):
            row = self.ns['tiny_memfd']({'seal': lambda fd: self.fail('seal after failed write')})
        self.assertFalse(row['ok']); self.assertEqual((row['stage'], row['errno']), ('WRITE', 28))
        self.assertNotIn('DO_NOT_EXPORT', stream.getvalue())
        with self.assertRaises(OSError): os.fstat(captured[0])


class ProcessTests(unittest.TestCase):
    def test_timeout_kills_owned_process_even_with_waiting_threadpool(self):
        code = "import concurrent.futures,time\nwith concurrent.futures.ThreadPoolExecutor(4) as p:\n p.submit(time.sleep,60)\n"
        started = time.monotonic()
        with mock.patch.object(P, 'CHILD', code):
            raw, rc, expired = P.run_child({}, .2)
        self.assertTrue(expired); self.assertEqual(rc, -9); self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(raw, b'')

    def test_partial_protocol_retains_stage_without_completion_claim(self):
        row = {'event': 'stage', 'label': 'parallel_0', 'phase': 'parallel_prefix', 'stage': 'READ', 'offset': 0}
        result = P.child_projection(b'NOX_TRANSPORT=' + json.dumps(row).encode() + b'\n')
        self.assertIsNone(result['complete']); self.assertEqual(result['incomplete_requests']['parallel_0'], row)


if __name__ == '__main__': unittest.main()
