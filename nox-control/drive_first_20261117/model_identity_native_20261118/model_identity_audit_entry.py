"""Existing owner audit entry; creates no files and sends no model requests."""
import json
import os
import re
import signal
import threading

import native_model_identity_readback as model


def run():
    # These are the existing operator's public command identity, not app env.
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    model.require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source),
                  'HOLD_IDENTITY_OWNER_CONTEXT')
    model.require(threading.current_thread() is threading.main_thread()
                  and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
                  'HOLD_IDENTITY_DEADLINE_CONTEXT')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(*_):
        raise model.Hold('HOLD_IDENTITY_HARD_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 20.0)
    reader = model.Reader()
    opened, fd = [], None
    try:
        opened = reader.directory(model.ROOT / 'state')
        fd = os.open('owner_maintenance.lock', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=opened[-1][0])
        report = model.observe(request, source, maintenance_lock_fd=fd)
        report['owner_context_environment_reads'] = 2
        report['audit_entry_writes'] = 0
        return report
    finally:
        if fd is not None:
            os.close(fd)  # Releases this entry's existing-file advisory lease.
        reader.close_dirs(opened)
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def main():
    try:
        report = run()
    except BaseException as exc:
        text = str(exc)
        code = text if isinstance(exc, model.Hold) and re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', text) else 'HOLD_IDENTITY_ENTRY'
        report = {'schema': 'NOX_BOUND_MODEL_REFERENCE_READBACK_V1', 'status': code,
                  'model_requests': 0, 'http_posts': 0, 'file_writes': 0, 'key_reads': 0,
                  'listener_model_reference_verified': False,
                  'owner_context_environment_reads': 2, 'audit_entry_writes': 0}
    encoded = model.canonical({'kind': 'model_identity_readback', 'data': report})
    if len(encoded) > model.MAX_OUTPUT - 128:  # Reserve both operator marker lines.
        report = {'schema': 'NOX_BOUND_MODEL_REFERENCE_READBACK_V1',
                  'status': 'HOLD_IDENTITY_ENTRY_OUTPUT_BOUND', 'model_requests': 0}
        encoded = model.canonical({'kind': 'model_identity_readback', 'data': report})
    complete = report.get('status') == 'BOUNDED_LISTENER_MODEL_REFERENCE_SNAPSHOT'
    print('NOX_MAINT_AUDIT=' + encoded.decode('utf8'), flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
