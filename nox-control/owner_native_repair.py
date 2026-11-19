"""Observe and, if fully qualified, stage the exact cold Engram service."""

from argparse import Namespace
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types


BUNDLE = __NOX_BUNDLE_JSON__
PINS = {"engram_cold_holder.py":"3ec79df376490c37300eb7ec78b5feb59463bc5abd976093331e5c305d4c62de","verify_ds41_backbone.py":"bfbdcda80899664e95a69b4669b51c5411796ecf977a9eee9cd15c9924c4a29e","owner_cold_stage_preflight.py":"c2e7e6887276166f9a692c90d586608f3e87c2a1320a4017ca500af4497cb412","atomic_engram_stage.py":"79b71a91f82b60e0761c5ed5bfe14723923ae69c9b70cebba048f338223e8e26","nox-engram-cold-holder.conf":"cc7a0c2ddb579005bf9a6cdd6ccac9e33f1010039f6b2fe984f1059655b036df","owner_ds41_launcher_diagnostic.py":"4670204894051bc05533d8d0c6e0f6d794daab3ff99da18085f434868e3ead28"}


def assets():
    if set(BUNDLE) != set(PINS):
        raise RuntimeError('HOLD_COLD_ENGRAM_ASSETS')
    data = {name: base64.b64decode(raw, validate=True) for name, raw in BUNDLE.items()}
    if any(not len(raw) <= 128 * 1024 or hashlib.sha256(raw).hexdigest() != PINS[name]
           for name, raw in data.items()):
        raise RuntimeError('HOLD_COLD_ENGRAM_ASSET_SHA')
    return data


def load(path, data):
    name = path.removesuffix('.py')
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(data[path], path, 'exec'), module.__dict__)
    return module


def cache_chat_gate_facts():
    marker = Path('/root/nox/state/chat_active')
    result = {}
    try:
        info = marker.lstat()
        result['chat_marker_regular_root'] = stat.S_ISREG(info.st_mode) and info.st_uid == 0
        result['chat_marker_recent_or_future'] = time.time() - info.st_mtime < 3
    except FileNotFoundError:
        result['chat_marker_present'] = False
    except OSError:
        result['chat_marker_unverified'] = True
    connection = http.client.HTTPConnection('127.0.0.1', 8098, timeout=2)
    try:
        connection.request('GET', '/slots', headers={'Connection': 'close'})
        response = connection.getresponse()
        result['slots_http_status'] = response.status
        raw = response.read(100001)
        if response.status == 200 and len(raw) <= 100000:
            slots = json.loads(raw)
            if isinstance(slots, list) and 1 <= len(slots) <= 64:
                flags = [[row[key] for key in ('is_processing', 'processing') if key in row]
                         for row in slots if isinstance(row, dict)]
                if len(flags) == len(slots) and all(row and all(type(x) is bool for x in row)
                                                     and len(set(row)) == 1 for row in flags):
                    result['slots'] = len(flags)
                    result['busy_slots'] = sum(row[0] for row in flags)
    except (OSError, ValueError, http.client.HTTPException):
        result['slots_unverified'] = True
    finally:
        connection.close()
    return result


def current_cache_result():
    try:
        fields = Path('/proc/747159/stat').read_text().rpartition(') ')[2].split()
        running = fields[19] == '189183257' and fields[0] not in ('Z', 'X')
        path = Path('/root/nox/logs/nox-cache-maintenance.log')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_size > 1024 ** 2 + 16384:
                return {'known_running_generation': running, 'receipt_verified': False}
            stream.seek(max(0, info.st_size - 65536))
            rows = stream.read(65537).splitlines()
        prefix = b'NOX_CACHE_MAINTENANCE='
        current = next((json.loads(row[len(prefix):]) for row in reversed(rows)
                        if row.startswith(prefix) and len(row) < 16384), {})
        fields = ('state', 'verified_candidate_count', 'page_cache_residency_reduction_bytes',
                  'observed_cgroup_headroom_delta_bytes')
        return {'known_running_generation': running, 'log_updated_unix': info.st_mtime,
                **{field: current[field] for field in fields if field in current}}
    except (OSError, ValueError, IndexError, TypeError):
        return {'receipt_verified': False}


def qualify_publication(report, scope, observer, launch):
    checks = report['checks']
    if not report['instance_bound'] or not checks:
        return False
    layout = observer.Layout()
    boot, _ = layout.file('/root/onstart.sh')
    mounted = layout.procfile('self/mountinfo', 1 << 20)
    destinations = (observer.HOLDER_PATH, observer.HOLDER_CONFIG)
    dirs_persistent = all(observer.disk_filesystem(mounted, os.fsencode(Path(target).parent))
                          for target in destinations)
    launch_state = launch.project(instance_id=60509551, expected_launcher_sha256=scope.launcher_sha256)
    checks['trusted_launcher'] = launch_state
    checks['publication_directories_persistent'] = dirs_persistent
    graph = checks.get('supervisor', {})
    pair = tuple(checks['staged_pair'][name]['state'] for name in ('holder', 'config'))
    stops = [Path('/root/nox') / name for name in observer.OWNER_STOP_MARKERS]
    return bool(
        hashlib.sha256(boot).hexdigest() == scope.onstart_sha256
        and b'/root/nox/ops/nox_teachers_warm.sh' not in boot
        and graph.get('model_config_sha256') == observer.MODEL_CONFIG_SHA
        and graph.get('model_guard_sha256') == scope.guard_sha256
        and graph.get('model_launcher_sha256') == scope.launcher_sha256
        and graph.get('configuration_explicit') is True and graph.get('teacher_autostart') is False
        and graph.get('holder_service_declared') == (pair == ('MATCH', 'MATCH'))
        and launch_state['trusted_existing_launch_candidate'] and dirs_persistent
        and pair in (('ABSENT', 'ABSENT'), ('MATCH', 'MATCH'))
        and checks.get('egress', {}).get('egress_reachable') is True
        and not any(os.path.lexists(item) for item in (*stops, Path('/workspace/NOX_STOP')))
    )


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if (os.geteuid() != 0 or not re.fullmatch('[1-9][0-9]{0,19}', request)
            or not re.fullmatch('[a-f0-9]{40}', source)):
        raise RuntimeError('HOLD_COLD_ENGRAM_OWNER')
    data = assets()
    print('NOX_MAINT_CACHE_CHAT_GATE=' + json.dumps(cache_chat_gate_facts(), separators=(',', ':')), flush=True)
    print('NOX_MAINT_CACHE_LATEST=' + json.dumps(current_cache_result(), separators=(',', ':')), flush=True)
    holder_name = 'engram_cold_holder.py'
    config_name = 'nox-engram-cold-holder.conf'
    load(holder_name, data)
    load('verify_ds41_backbone.py', data)
    observer = load('owner_cold_stage_preflight.py', data)
    launch = load('owner_ds41_launcher_diagnostic.py', data)
    installer = load('atomic_engram_stage.py', data)
    request_scope = Namespace(
        instance_id=60509551, request_id=request, source_sha=source,
        onstart_sha256='b36b916aadc8bb6047108823bf7b86f00448deafd9f79a824a9f4924c1190507',
        guard_sha256='b280bc46218d37a1480680a3d842c9b53d71a3d567c07606a1fb54878188d777',
        launcher_sha256='50a4e198bcfed2e7965220e897c349db50eb17dd9560243827c9a085923e6638',
        holder_sha256=PINS[holder_name], config_sha256=PINS[config_name],
    )
    report = observer.collect(request_scope, container_label=os.environ.get('VAST_CONTAINERLABEL'),
                              container_id=os.environ.get('CONTAINER_ID'))
    report['stage_only_scope'] = True
    report['stage_eligible'] = qualify_publication(report, request_scope, observer, launch)
    print('NOX_MAINT_ENGRAM_COLD_PREFLIGHT=' + json.dumps(report, separators=(',', ':')), flush=True)
    if report['stage_eligible']:
        deadline = time.monotonic() + 25
        while True:
            try:
                receipt = installer.stage_cold_holder(
                    source_sha=source, request_id=request, preflight=report,
                    holder=data[holder_name], holder_sha256=PINS[holder_name],
                    config=data[config_name], config_sha256=PINS[config_name],
                )
                break
            except installer.StageHold as error:
                if str(error) != 'HOLD_COLD_STAGE_OWNER_LEASE_BUSY' or time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        print('NOX_MAINT_ENGRAM_COLD_STAGE=' + json.dumps(receipt, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        code = str(error)
        print('NOX_MAINT_ENGRAM_COLD_HOLD=' + (code if re.fullmatch(r'[A-Z][A-Z0-9_]{2,80}', code)
                                               else type(error).__name__), flush=True)
        raise SystemExit(2) from None
