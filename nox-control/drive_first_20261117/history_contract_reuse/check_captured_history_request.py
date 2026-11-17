#!/usr/bin/env python3
"""Capture the frozen client request locally; never call run() or any socket."""
import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
CORE = ROOT.parent / 'native_resonance_patch/native_acceptance.py'
EXPECTED_CORE = '7b82ccbb235bd51c9a4782919aa6cfd484ad96e253ef0c2cebd9c61ca8e2ef9e'
if hashlib.sha256(CORE.read_bytes()).hexdigest() != EXPECTED_CORE:
    raise RuntimeError('HOLD_FIXTURE_CORE_CHANGED')
spec = importlib.util.spec_from_file_location('frozen_local_acceptance_fixture', CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class Response:
    status = 200
    headers = {'Content-Type': 'application/json'}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, bound): return b'{}'

class Capture:
    def __init__(self): self.requests = []
    def open(self, request, timeout):
        self.requests.append(request)
        return Response()

client = core.LoopbackClient(read_only=True)
capture = Capture()
client.opener = capture
client.history_evidence(core.RECONCILE_DIALOG_ID)
if len(capture.requests) != 1:
    raise AssertionError('Exactly one local request object expected')
request = capture.requests[0]
expected = core.BASE + '/api/ui/memory/dialogs/history?dialog_id=' + core.RECONCILE_DIALOG_ID + '&limit=2'
query = parse_qs(urlsplit(request.full_url).query, strict_parsing=True)
if request.full_url != expected or request.get_method() != 'GET' or request.data is not None:
    raise AssertionError('Request construction changed')
if query != {'dialog_id': [core.RECONCILE_DIALOG_ID], 'limit': ['2']}:
    raise AssertionError('Query differs from the exact fixed own-dialog contract')
result = {'status': 'PASS_LOCAL_CAPTURE_ONLY', 'core_sha256': EXPECTED_CORE,
          'request_count': 1, 'method': request.get_method(),
          'request_body': None, 'exact_fixed_own_dialog_url': True,
          'query_keys': sorted(query), 'limit': query['limit'],
          'real_network_requests': 0, 'native_code_imported': False}
print(json.dumps(result, indent=2))
