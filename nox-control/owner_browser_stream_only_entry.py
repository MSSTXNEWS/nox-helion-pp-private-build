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
    'owner_chat_browser_qa.py': '87e098cacfb4063cc9d2ff1d6d80dcba895dc6ac482789ddd2968d848454aa08',
    'owner_chat_browser_transport_qa.py': 'e9b15663416bd03b7579cf8c3788e835be6713925d12a4cae5d4daf3b74737ee',
    'owner_chat_browser_release_qa.py': '43db260f5a40323a2429773b2c9e568c64e477f769889d85b5ac21afa12a0f59',
    'owner_chat_stream_only_qa.py': '684e064e9ab1dad821ed5ed80b521c31395ec70a8bfc1e37df7ee77fb953304f',
}
ENV_SPEC = {'schema': 'NOX_OWNER_BROWSER_ENV_V1', 'playwright': '1.65.2',
            'base_python': '/root/nox/venv/bin/python', 'torch_modified': False}
PREFIX = 'NOX_MAINT_BROWSER_QA='


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
    paths.extend((Path('/workspace/NOX_STOP'), ROOT / 'state' / 'OWNER_MAINTENANCE.flag'))
    return any(path.exists() or path.is_symlink() for path in paths)


def child_environment(request, source):
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'LD_LIBRARY_PATH') if key in os.environ}
    # The served HTML digest must come from the authenticated owner/install
    # context. Never synthesize it from the page, source bundle or build tag.
    served_pin = os.environ.get('NOX_OWNER_EXPECTED_SERVED_HTML_SHA256')
    require(isinstance(served_pin, str)
            and re.fullmatch(r'[0-9a-f]{64}', served_pin) is not None,
            'SERVED_HTML_SHA256_PIN_MISSING')
    env.update(CUDA_VISIBLE_DEVICES='', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               PLAYWRIGHT_BROWSERS_PATH=str(AREA / 'browsers'),
               NOX_OWNER_REQUEST_ID=request, NOX_OWNER_SOURCE_SHA=source,
               NOX_OWNER_EXPECTED_SERVED_HTML_SHA256=served_pin)
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
    # Bootstrap may consume RAM/disk after the original admission. Recheck
    # immediately before spawning the disposable browser child.
    resource_budget()
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
        records = value.get('native_terminal_done_records')
        records_shape = (isinstance(records, list) and len(records) in (0, 2)
                         and all(isinstance(item, dict)
                                 and set(item) == {'saved', 's03_integrated', 'dialog_id_matches'}
                                 and type(item.get('saved')) is bool
                                 and type(item.get('s03_integrated')) is bool
                                 and type(item.get('dialog_id_matches')) is bool
                                 for item in records))
        require(value.get('schema') == 'NOX_OWNER_BROWSER_STREAM_ONLY_QA_V2'
                and value.get('request') == request and value.get('source_sha') == source
                and value.get('full_browser_qa_promoted') is False
                and value.get('upstream_model_inference_verified') is False
                and value.get('two_turn_mode') is True
                and value.get('maximum_new_dialogs') == 1
                and value.get('maximum_native_posts') == 2
                and type(value.get('first_turn_terminal_sse_verified')) is bool
                and type(value.get('authenticated_s03_history_readback_verified')) is bool
                and value.get('canonical_s03_receipt_verified') is False
                and value.get('canonical_s03_receipt_provider_present') is False
                and type(value.get('owner_authenticated_history_readback_gets')) is int
                and value.get('owner_authenticated_history_readback_gets') in (0, 1)
                and type(value.get('native_posts_admitted')) is int
                and 0 <= value.get('native_posts_admitted') <= 2
                and type(value.get('both_terminal_sse_done_records_saved_s03_integrated')) is bool
                and type(value.get('same_dialog_id')) is bool
                and records_shape, 'CHILD_SCOPE')
    if proc.returncode == 0:
        records = value['native_terminal_done_records']
        require(row['kind'] == 'browser_stream_only_receipt'
                and value.get('state') == 'STREAM_ONLY_ACCEPTED'
                and value.get('stream_only_acceptance_verified') is True
                and value.get('native_posts_admitted') == 2
                and value.get('first_turn_terminal_sse_verified') is True
                and value.get('both_terminal_sse_done_records_saved_s03_integrated') is True
                and value.get('same_dialog_id') is True
                and len(records) == 2
                and all(item['saved'] is True and item['s03_integrated'] is True
                        and item['dialog_id_matches'] is True for item in records)
                and value.get('authenticated_s03_history_readback_verified') is True
                and value.get('owner_authenticated_history_readback_gets') == 1
                and value.get('canonical_s03_receipt_verified') is False
                and value.get('owner_auth_verified') ==
                    {'anonymous_status': 401, 'login_status': 200, 'session_status': 200},
                'CHILD_ACCEPTANCE')
    emit(row['kind'], value)
    return 0 if proc.returncode == 0 else 2



def _checked_install(args, env, hold_code, timeout_sec=180):
    """Only fixed argv, fixed version, private QA area; never use shell."""
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, timeout=timeout_sec, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('HOLD_BROWSER_BOOTSTRAP_' + hold_code) from exc
    require(result.returncode == 0, 'BOOTSTRAP_' + hold_code)


def ensure_runtime(request):
    """Repair a missing *isolated QA* venv, not the production UI/model/S03.

    No existing private QA directory is deleted. An incomplete old QA area is
    preserved under a request-scoped backup before atomic promotion. Failures
    restore it and remove only this attempt's temporary build.
    """
    try:
        return existing_runtime(), False
    except FileNotFoundError:
        pass
    # No repair of a mismatched/symlinked/foreign-owner runtime: those are holds.
    resource_budget()
    plain_directory(ROOT)
    base = Path(ENV_SPEC['base_python'])
    require(base.is_file() and os.access(base, os.X_OK), 'BOOTSTRAP_BASE_PYTHON')
    request = str(request)
    require(bool(re.fullmatch(r'[0-9]{1,24}', request)), 'BOOTSTRAP_REQUEST')
    staging = Path(tempfile.mkdtemp(prefix='.nox-browserqa-', dir=str(ROOT)))
    backup = ROOT / ('browser_qa.previous.' + request)
    require(not backup.exists() and not backup.is_symlink(), 'BOOTSTRAP_BACKUP_COLLISION')
    os.chmod(staging, 0o700)
    # A failed promotion may only remove the directory created by this attempt.
    staged_info = staging.stat(follow_symlinks=False)
    staged_identity = (staged_info.st_dev, staged_info.st_ino)
    original_moved = False
    promoted = False
    try:
        venv = staging / 'venv'
        # The checkout's Python is reused, but all packages/browser files go
        # to private new paths. Do not upgrade torch/NOX environment.
        sys_env = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'LANG': 'C.UTF-8', 'HOME': str(staging),
            'PIP_NO_INPUT': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
            'PYTHONNOUSERSITE': '1',
            'PLAYWRIGHT_BROWSERS_PATH': str(staging / 'browsers'),
        }
        _checked_install([str(base), '-m', 'venv', '--copies', str(venv)],
                         sys_env, 'VENV', 90)
        child = venv / 'bin/python'
        require(child.is_file() and os.access(child, os.X_OK), 'BOOTSTRAP_PYTHON')
        _checked_install([
            str(child), '-m', 'pip', 'install', '--no-cache-dir',
            '--only-binary=:all:', 'playwright==1.65.2'],
            sys_env, 'PIP', 200)
        _checked_install([str(child), '-m', 'playwright', 'install', 'chromium'],
                         sys_env, 'CHROMIUM', 260)
        _checked_install([str(child), '-I', '-B', '-c',
                          "import importlib.metadata as m; assert m.version('playwright')=='1.65.2'"],
                         sys_env, 'VERSION', 20)
        marker = staging / 'owner-environment.json'
        raw = json.dumps(ENV_SPEC, sort_keys=True, separators=(',', ':')).encode()
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, raw); os.fsync(fd)
        finally:
            os.close(fd)
        require(shutil.disk_usage(ROOT).free >= 7 * 1024**3, 'BOOTSTRAP_DISK_RESERVE')
        require(not stop_present(), 'OWNER_STOP')
        if AREA.exists() or AREA.is_symlink():
            # No unknown symlink, world-writable or foreign-owned backup.
            plain_directory(AREA, private=True)
            AREA.rename(backup)
            original_moved = True
        staging.rename(AREA)
        promoted = True
        python = existing_runtime()
        return python, True
    except Exception:
        if promoted:
            # A failed post-promotion runtime validation must not strand the
            # previous QA runtime in backup or leave an unverified candidate live.
            current = AREA.stat(follow_symlinks=False)
            require((current.st_dev, current.st_ino) == staged_identity
                    and not staging.exists() and not staging.is_symlink(),
                    'BOOTSTRAP_ROLLBACK_IDENTITY')
            AREA.rename(staging)
            promoted = False
        if original_moved and not promoted and backup.exists():
            backup.rename(AREA)
        raise
    finally:
        if staging.exists() and staging.is_dir() and not staging.is_symlink():
            current = staging.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) == staged_identity:
                shutil.rmtree(staging)

def main():
    blobs = sources(); program = child_program(blobs)
    compile(program, '<stream-only-child>', 'exec')
    request, source = owner_context(); resources = resource_budget(); python, bootstrap_performed = ensure_runtime(request)
    emit('browser_stream_only_sources', {'source_pins': PINS,
        'composed_child_sha256': hashlib.sha256(program).hexdigest(), 'existing_runtime_only': True,
        'production_ui_changed': False, 'full_qa_scope_unchanged': True, 'resources_before_launch': resources,
        'isolated_runtime_bootstrapped': bootstrap_performed})
    rc = run_child(python, program, request, source)
    if rc == 0:
        print('NOX_MAINT_BROWSER_QA_COMPLETE=true', flush=True)
    return rc


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        emit('browser_stream_only_entry_hold', {'reason': safe(exc), 'private_exception_exported': False})
        raise SystemExit(2)
