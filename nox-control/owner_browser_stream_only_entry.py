#!/usr/bin/env python3
"""Run a single stream-only QA in the already installed isolated CPU browser.

No package, browser, proxy, model, service or production file is installed here.
Only the private QA receipt and the one authorized public test dialog are new.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import tempfile

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
AREA = ROOT / 'browser_qa'
PINS = {
    'owner_chat_browser_qa.py': '9530c6e71274bbbca997f0aea07a26c988cfd536ed1aa1ba4067753827ac56f9',
    'owner_chat_browser_transport_qa.py': '360c155642ccdb43f39acf7b493068d3d2ac906bfd761c60d8c5ee51d48507fe',
    'owner_chat_browser_release_qa.py': 'eaa8af0e229c9ce0a730b7b472f8b9b8a1018fbd5cf7b8518890342d9d7047cb',
    'owner_chat_stream_only_qa.py': '20107d12ece5bf0575abf5603674534b80b253c8708164da4b30cc3c371bacd6',
}
ENV_SPEC = {'schema': 'NOX_OWNER_BROWSER_ENV_V1', 'playwright': '1.65.2',
            'base_python': '/root/nox/venv/bin/python', 'torch_modified': False}
PREFIX = 'NOX_MAINT_REPAIR='


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_STREAM_ONLY_ENTRY_' + code)


def safe(exc):
    value = str(exc)
    return value if re.fullmatch(r'HOLD_[A-Z0-9_]{1,120}', value) else type(exc).__name__


def emit(kind, data):
    print(PREFIX + json.dumps({'kind': kind, 'data': data}, separators=(',', ':'), allow_nan=False), flush=True)


def sources():
    values = {}
    for name, pin in PINS.items():
        value = BUNDLE.get(name)
        require(isinstance(value, str) and 0 < len(value) <= 350000, 'BUNDLE_BOUND')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 262144 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        compile(raw, name, 'exec'); values[name] = raw
    return values


def child_program(blobs):
    items = {name[:-3]: {'raw': base64.b64encode(raw).decode(), 'sha256': PINS[name]}
             for name, raw in blobs.items()}
    return ("import base64,hashlib,importlib.metadata,json,sys,types\n"
        "sys.dont_write_bytecode=True\n"
        "if sys.prefix!='/root/nox/browser_qa/venv' or importlib.metadata.version('playwright')!='1.65.2':raise RuntimeError('HOLD_STREAM_ONLY_EXISTING_RUNTIME')\n"
        "items=" + repr(items) + "\n"
        "loaded={}\n"
        "for name,item in items.items():\n"
        " raw=base64.b64decode(item['raw'],validate=True)\n"
        " if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise RuntimeError('HOLD_STREAM_ONLY_CHILD_PIN')\n"
        " mod=types.ModuleType('_nox_stream_only_'+name);mod.__file__='<'+name+'>'\n"
        " sys.modules[mod.__name__]=mod\n"
        " exec(compile(raw,mod.__file__,'exec'),mod.__dict__);loaded[name]=(mod,raw)\n"
        "core,raw=loaded['owner_chat_browser_qa']\n"
        "transport,traw=loaded['owner_chat_browser_transport_qa']\n"
        "release,rraw=loaded['owner_chat_browser_release_qa']\n"
        "scope=loaded['owner_chat_stream_only_qa'][0]\n"
        "try:\n"
        " scope.install(core,raw,transport,traw,release,rraw)\n"
        " rc=scope.main(core)\n"
        "except Exception as exc:\n"
        " core.emit('browser_stream_only_hold',{'reason':core.safe_error(exc),'private_exception_exported':False});rc=2\n"
        "raise SystemExit(rc)\n").encode()


def plain_directory(path, private=False):
    for item in (*reversed(path.parents), path):
        require(not item.is_symlink(), 'RUNTIME_PATH')
    info = path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022,
            'RUNTIME_DIRECTORY')
    if private:
        require(stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_RUNTIME')


def read_private(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= limit, 'RUNTIME_MARKER')
        raw = os.read(fd, limit + 1); after = os.fstat(fd)
        ident = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        require(len(raw) == before.st_size and ident(before) == ident(after), 'RUNTIME_MARKER_CHANGED')
        return raw
    finally:
        os.close(fd)


def existing_runtime():
    plain_directory(AREA, private=True)
    require(json.loads(read_private(AREA / 'owner-environment.json', 4096)) == ENV_SPEC, 'RUNTIME_SCOPE')
    venv = AREA / 'venv'; plain_directory(venv); plain_directory(venv / 'bin')
    # venv python is normally a symlink to the existing owner Python binary.
    # Its target must be a regular, owner-controlled executable, never created.
    python = venv / 'bin/python'; target = python.resolve(strict=True); info = target.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022
            and os.access(python, os.X_OK), 'EXISTING_PYTHON')
    return python


def owner_context():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(bool(re.fullmatch('[0-9]{1,24}', request)) and bool(re.fullmatch('[a-f0-9]{40}', source)), 'OWNER_CONTEXT')
    return request, source


def stop_present():
    paths = [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')]
    paths.append(Path('/workspace/NOX_STOP'))
    return any(path.exists() or path.is_symlink() for path in paths)


def child_environment(request, source):
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH') if key in os.environ}
    env.update(CUDA_VISIBLE_DEVICES='', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PLAYWRIGHT_BROWSERS_PATH=str(AREA / 'browsers'),
               NOX_OWNER_REQUEST_ID=request, NOX_OWNER_SOURCE_SHA=source)
    return env


def resource_budget():
    require(not stop_present(), 'OWNER_STOP')
    disk = shutil.disk_usage(ROOT).free
    require(disk >= 7 * 1024 ** 3, 'DISK_RESERVE')
    maximum = (Path('/sys/fs/cgroup') / 'memory.max').read_text().strip()
    current = (Path('/sys/fs/cgroup') / 'memory.current').read_text().strip()
    require(maximum.isdigit() and current.isdigit(), 'RAM_UNKNOWN')
    headroom = int(maximum) - int(current)
    require(headroom >= 4 * 1024 ** 3, 'RAM_RESERVE')
    return {'disk_free_bytes': disk, 'cgroup_headroom_bytes': headroom}


def run_child(python, program, request, source):
    require(not stop_present(), 'OWNER_STOP')
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen([str(python), '-I', '-B', '-'], stdin=subprocess.PIPE, stdout=output, stderr=errors,
                                env=child_environment(request, source), start_new_session=True)
        try:
            proc.communicate(program, timeout=165)
        except subprocess.TimeoutExpired:
            # Only this disposable QA process group is terminated; no service,
            # model, trainer or another owner's browser belongs to that group.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.communicate(timeout=5)
            raise RuntimeError('HOLD_STREAM_ONLY_ENTRY_CHILD_TIMEOUT') from None
        require(output.tell() <= 262144 and errors.tell() <= 1048576, 'CHILD_OUTPUT_BOUND')
        output.seek(0); raw = output.read(262145)
    rows = []
    for line in raw.decode('utf-8', 'replace').splitlines():
        if not line.startswith(PREFIX):
            continue
        require(len(line) <= 100000, 'CHILD_ROW_BOUND')
        row = json.loads(line[len(PREFIX):])
        if row.get('kind') not in ('browser_stream_only_receipt', 'browser_stream_only_hold'):
            continue
        rows.append(row)
    require(len(rows) == 1 and isinstance(rows[0].get('data'), dict), 'CHILD_RESULT')
    row = rows[0]; value = row['data']
    if row['kind'] == 'browser_stream_only_receipt':
        require(value.get('schema') == 'NOX_OWNER_BROWSER_STREAM_ONLY_QA_V1'
                and value.get('request') == request and value.get('source_sha') == source
                and value.get('full_browser_qa_promoted') is False
                and value.get('upstream_model_inference_verified') is False, 'CHILD_SCOPE')
    if proc.returncode == 0:
        require(row['kind'] == 'browser_stream_only_receipt' and value.get('state') == 'STREAM_ONLY_ACCEPTED'
                and value.get('stream_only_acceptance_verified') is True, 'CHILD_ACCEPTANCE')
    emit(row['kind'], value)
    return 0 if proc.returncode == 0 else 2


def main():
    blobs = sources(); program = child_program(blobs)
    compile(program, '<stream-only-child>', 'exec')
    request, source = owner_context(); python = existing_runtime(); resources = resource_budget()
    emit('browser_stream_only_sources', {'source_pins': PINS,
        'composed_child_sha256': hashlib.sha256(program).hexdigest(), 'existing_runtime_only': True,
        'production_ui_changed': False, 'full_qa_scope_unchanged': True, 'resources_before_launch': resources})
    rc = run_child(python, program, request, source)
    if rc == 0:
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return rc


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('browser_stream_only_entry_hold', {'reason': safe(exc), 'private_exception_exported': False})
        raise SystemExit(2)
