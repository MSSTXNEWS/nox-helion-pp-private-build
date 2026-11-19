"""Owner-authorized, one-group NOX cache service installation."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types


BUNDLE = __NOX_BUNDLE_JSON__
PINS = {"nox_cache_maintenance.py":"5113e633d66026b5821394a3d9e87433ddc14711fe59df1f09ff0dd6974a593c","owner_memory_cleanup_entry.py":"a308933a6df312ad6601bebae4e39ef8f0cd9794cea0f9c4ebc325ea45aac403","owner_memory_governor.py":"9cdcc97d333a4b2ea07f3003930f260d567a2b6a7cdebb1adcd36220befe617b","owner_storage_reclaim.py":"085403de23d817f1f1307df757901b914115c4745a78dea7ddda53a7fca350f8","nox-cache-maintenance.conf":"9c3eb4d108fa640936a05e178c3ec4f63cc3083c3c4aa7d0a1ac8074d79c09ad","atomic_engram_stage.py":"79b71a91f82b60e0761c5ed5bfe14723923ae69c9b70cebba048f338223e8e26","owner_supervisor_background_release.py":"1928cc0b4ab308f65f329a992376963769b1870984562a9fc12a213a2578b43a","owner_cache_maintenance_activation.py":"7e942d8d857178e24b2a7a19e4b7d149a504d8a280a43a4ba39151160765cedf","owner_teacher_boot_diff.py":"371913c596cf7cc6b55ecbd17cc920becfc6bc183db13b79d23d07a31a8a4a2c","owner_disable_teacher_boot.py":"ce1a08e6b9c667dd01f78e016adbea22399b8da5535bc7b375bb119ca43f668a","owner_remove_exact_teacher_line.py":"35ad19ddb608cb61462b2629243e9ec3919490e20f16934492693e55085d58ad"}
BOOT = '9c0ecc02-85c1-452b-b8ae-521e9a11fd03'
PID1 = 167790899
SUPERVISOR = (114, 167791115)
MAIN = 'fcead12b4dcb7f56b31d223f1cfa89792bd6e8008f78708a831b41fab9ece25d'
CACHE_LOG = Path('/root/nox/logs/nox-cache-maintenance.log')


def need(condition, reason):
    if not condition:
        raise RuntimeError('HOLD_CACHE_ENTRY_' + reason)


def sources():
    need(isinstance(BUNDLE, dict) and set(BUNDLE) == set(PINS), 'ASSET_SCOPE')
    data = {}
    for name, content in BUNDLE.items():
        raw = base64.b64decode(content, validate=True)
        need(0 < len(raw) < 256 * 1024 and hashlib.sha256(raw).hexdigest() == PINS[name], 'ASSET_SHA')
        data[name] = raw
    return data


def module(name, data):
    loaded = types.ModuleType(name)
    sys.modules[name] = loaded
    exec(compile(data[name + '.py'], name + '.py', 'exec'), loaded.__dict__)
    return loaded


def service_receipt(activated_at):
    deadline = time.monotonic() + 32
    while time.monotonic() < deadline:
        try:
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            with os.fdopen(os.open(CACHE_LOG, flags), 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (stat.S_ISREG(info.st_mode) and info.st_uid == 0
                        and info.st_size <= 1024 ** 2 + 16384 and info.st_mtime >= activated_at):
                    raw = stream.read(1024 ** 2 + 16385)
                    prefix = b'NOX_CACHE_MAINTENANCE='
                    for line in reversed(raw.splitlines()):
                        if line.startswith(prefix) and len(line) < 16384:
                            report = json.loads(line[len(prefix):])
                            if isinstance(report, dict) and isinstance(report.get('state'), str):
                                return report
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return {'state': 'FIRST_CYCLE_NOT_OBSERVED'}


def record_hold(phase, error):
    code = str(error)
    print('NOX_MAINT_' + phase + '_HOLD=' + (
        code if re.fullmatch(r'[A-Z][A-Z0-9_]{2,80}', code)
        else type(error).__name__ + ('_' + str(error.errno) if isinstance(error, OSError) else '')),
          flush=True)


def install_cache(source, request, data):
    module('atomic_engram_stage', data)
    native = module('owner_supervisor_background_release', data)
    activate = module('owner_cache_maintenance_activation', data)
    main = native.read(activate.MAIN, 256 << 10, rooted=True)
    need(hashlib.sha256(main).hexdigest() == MAIN, 'SUPERVISOR_MAIN_CHANGED')
    daemon = native.process(SUPERVISOR[0])
    need(native.process(1)[:2] == (PID1, 0) and daemon[:2] == (SUPERVISOR[1], 1), 'SUPERVISOR_EPOCH')
    parsed = native.config_parse(main)
    endpoint = native.resolve_socket(native.plain_socket_path(parsed['unix_http_server']['file'], activate.MAIN.parent))
    files = sorted(path for path in activate.INCLUDES.iterdir()
                   if path.name.endswith('.conf') and path.name != activate.UNIT_NAME)
    need(len(files) <= 96, 'SUPERVISOR_INCLUDE_CENSUS')
    include = tuple((path.name, hashlib.sha256(native.read(path, 256 << 10, rooted=True)).hexdigest())
                    for path in files)
    now = time.time()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    need(boot == BOOT, 'SUPERVISOR_BOOT_CHANGED')
    argv = native.read(Path(f'/proc/{SUPERVISOR[0]}/cmdline'), 16 << 10)
    pin = activate.OwnerPin(request, source, now, now + 150, BOOT, PID1, *SUPERVISOR,
                            hashlib.sha256(argv).hexdigest(), MAIN, str(endpoint), include,
                            PINS[activate.UNIT_NAME], tuple((name, PINS[name]) for name in activate.WORKERS))

    def owner(passed, scope):
        return (passed == pin and scope in ('activate', 'parse', 'add', 'rollback_stop', 'rollback_remove')
                and time.time() < pin.expires_at
                and os.environ.get('NOX_OWNER_SOURCE_SHA') == source
                and os.environ.get('NOX_OWNER_REQUEST_ID') == request)

    result = activate.activate_cache_maintenance(
        pin, workers={name: data[name] for name in activate.WORKERS},
        unit=data[activate.UNIT_NAME], authorize=owner,
    )
    return result, now


def main():
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    need(os.geteuid() == os.getegid() == 0 and re.fullmatch(r'[a-f0-9]{40}', source)
         and re.fullmatch(r'[1-9][0-9]{0,19}', request), 'OWNER_REQUEST')
    data = sources()

    teacher = None
    try:
        module('owner_teacher_boot_diff', data)
        module('owner_disable_teacher_boot', data)
        warm = module('owner_remove_exact_teacher_line', data)
        root = Path('/root/nox')
        stops = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
                 'state/STOP', 'state/STOP.flag', 'state/OWNER_MAINTENANCE.flag')
        need(warm.pid1_start() == PID1 and not any(os.path.lexists(root / path) for path in stops)
             and not os.path.lexists('/workspace/NOX_STOP'), 'TEACHER_OWNER_SCOPE')
        teacher = warm.remove_exact_teacher_line(
            instance_id=60509551, phase2_request='7011341488',
            phase2_source='8e5f6ef0bd034c7617edeb6711d4f2aa15f58932', apply=True,
        )
        print('NOX_MAINT_TEACHER_BOOT_UPDATE=' + json.dumps(teacher, separators=(',', ':')), flush=True)
    except Exception as error:
        record_hold('TEACHER_BOOT_UPDATE', error)

    result = None
    now = time.time()
    try:
        result, now = install_cache(source, request, data)
        print('NOX_MAINT_CACHE_ACTIVATION=' + json.dumps(result, separators=(',', ':')), flush=True)
    except Exception as error:
        record_hold('CACHE_ACTIVATION', error)

    if result and result['added']:
        print('NOX_MAINT_CACHE_FIRST_CYCLE=' + json.dumps(service_receipt(now), separators=(',', ':')), flush=True)
    need(result is not None or teacher is not None, 'SERVICE_CHANGES_HELD')
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        record_hold('SERVICE_CHANGE', error)
        raise SystemExit(2) from None
