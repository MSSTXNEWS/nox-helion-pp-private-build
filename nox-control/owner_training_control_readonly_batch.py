#!/usr/bin/env python3
"""Run three pinned, read-only observations in one owner maintenance session."""
import base64
import contextlib
import hashlib
import io
import json
import signal
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

SOURCES = (
    ('owner_qwen_transport_budget_observe.py',
     '4ee681efb9ee2587b01a3f9e952bfc6530b5d8a5f416c116f2460a2a6983261c',
     'qwen_execution_revision_observation'),
    ('owner_admin_control_structure_probe.py',
     '9ba93c23b7ead795ae94f44d704970d904ccce119b27262557d54d5538965ca3',
     'admin_delegated_control_structure'),
    ('owner_qwen_public_memfd_access_probe.py',
     '6f1286678d653af5a0f0aecedccf66b08639659df6213ff7b2f2cf8f48cfd473',
     'qwen_public_memfd_access_probe'),
)


class Deadline(BaseException):
    pass


def main():
    statuses = []
    previous = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise Deadline()

    for name, pin, kind in SOURCES:
        started = time.monotonic()
        capture = io.StringIO()
        code = 2
        try:
            encoded = BUNDLE.get(name)
            if not isinstance(encoded, str) or len(encoded) > 131072:
                raise ValueError('source scope')
            raw = base64.b64decode(encoded, validate=True)
            if hashlib.sha256(raw).hexdigest() != pin:
                raise ValueError('source pin')
            signal.signal(signal.SIGALRM, expired)
            signal.alarm(90)
            module = types.ModuleType('_nox_readonly_' + name.removesuffix('.py'))
            module.__file__ = '/root/nox/scripts/' + name
            with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                exec(compile(raw, module.__file__, 'exec'), module.__dict__)
                code = module.main()
            value = capture.getvalue()
            if len(value.encode()) > 262144:
                raise ValueError('output scope')
            lines = [line[len('NOX_MAINT_REPAIR='):] for line in value.splitlines()
                     if line.startswith('NOX_MAINT_REPAIR=')]
            if len(lines) != 1:
                raise ValueError('record count')
            record = json.loads(lines[0])
            if record.get('kind') != kind or not isinstance(record.get('data'), dict):
                raise ValueError('record scope')
        except (Exception, Deadline) as exc:
            code = 2
            record = {'kind': kind, 'data': {'state': 'READ_ONLY_OBSERVATION_UNAVAILABLE',
                      'reason': type(exc).__name__.upper(), 'read_only': True}}
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        print('NOX_MAINT_REPAIR=' + json.dumps(record, sort_keys=True,
              separators=(',', ':'), allow_nan=False), flush=True)
        statuses.append({'source': name, 'sha256': pin, 'success': code == 0,
                         'elapsed_seconds': round(time.monotonic() - started, 3)})
    success = all(row['success'] for row in statuses)
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'read_only_batch_summary',
          'data': {'state': 'OBSERVED' if success else 'PARTIAL', 'read_only': True,
                   'observations': statuses}}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(success).lower(), flush=True)
    return 0 if success else 2


if __name__ == '__main__':
    raise SystemExit(main())
