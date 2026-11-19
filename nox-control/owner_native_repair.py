"""Report memory of exact registered NOX background units without stopping them."""

import base64
from hashlib import sha256
import json
import os
import re
from types import ModuleType


BUNDLE = __NOX_BUNDLE_JSON__
SUPERVISOR = 'owner_supervisor_background_probe.py'
PIN = '42cf5e308dad69823e16eef91d2d31561c9bf05b6374903bccc5dd239ddf8981'
GROUPS = (
    'nox-dialog-miner', 'nox-kb-eventlistener', 'nox-lifeline-guard', 'nox-selfheal',
    'nox-cache-maintenance', 'nox-dispatcher', 'nox-dispatcher-t855u',
    'nox-fill-idle-t166u', 'nox-gpu-idle-t170u',
)
FIELDS = ('Pss_Anon', 'Pss_File', 'Pss_Shmem', 'Private_Clean', 'Private_Dirty')


def native_control():
    if set(BUNDLE) != {SUPERVISOR}:
        raise RuntimeError('HOLD_MEMORY_CENSUS_BUNDLE')
    raw = base64.b64decode(BUNDLE[SUPERVISOR], validate=True)
    if sha256(raw).hexdigest() != PIN:
        raise RuntimeError('HOLD_MEMORY_CENSUS_PIN')
    control = ModuleType('nox_memory_census_supervisor')
    exec(compile(raw, SUPERVISOR, 'exec'), control.__dict__)
    control.TARGETS = GROUPS
    if control.STOP_TARGET is not None:
        raise RuntimeError('HOLD_MEMORY_CENSUS_READ_ONLY_SCOPE')
    return control


def profile(control, name):
    row = control.status(name)
    result = {'state': row['statename']}
    pid = row.get('pid')
    if row['statename'] != 'RUNNING' or type(pid) is not int or pid <= 1:
        return result
    ticks, ppid, group, state = control.process(pid)
    control.need(ppid == control.SUPERVISOR[0] and group == pid
                 and state not in (b'Z', b'X')
                 and control.cgroup(pid) == control.cgroup('self'), 'WORKER_GENERATION')
    directory = control.PROC / str(pid)
    raw = control.read(directory / 'smaps_rollup', 8192).decode()
    values = dict(re.findall(r'(?m)^([A-Za-z_]+):\s+([0-9]+) kB$', raw))
    control.need(all(field in values for field in FIELDS), 'WORKER_MEMORY_FIELDS')
    control.need(control.process(pid)[:3] == (ticks, ppid, group), 'WORKER_GENERATION_CHANGED')
    result.update(pid=pid, start_ticks=ticks, memory_bytes={key: 1024 * int(values[key]) for key in FIELDS})
    return result


def main():
    control = native_control()
    labels = {os.environ[name].removeprefix('C.') for name in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(name)}
    control.need(os.geteuid() == 0 and labels == {'60509551'}
                 and re.fullmatch(r'[1-9][0-9]{0,19}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
                 and re.fullmatch(r'[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', ''))
                 and control.read(control.PROC / 'sys/kernel/random/boot_id', 128).decode().strip() == control.BOOT,
                 'OWNER_CONTEXT')
    control.protect_model()
    before = control.memory()
    groups = {}
    for name in GROUPS:
        try:
            groups[name] = profile(control, name)
        except (OSError, RuntimeError, ValueError, KeyError, control.subprocess.TimeoutExpired):
            groups[name] = {'state': 'UNVERIFIED'}
    control.protect_model()
    after = control.memory()
    for item in (before, after):
        item['raw_headroom'] = item['limit'] - item['current']
    print('NOX_MAINT_MEMORY_BACKGROUND_CENSUS=' + json.dumps(
        {'before': before, 'after': after, 'registered_groups': groups,
         'model_generation_preserved': True, 'authority': 'READ_ONLY', 'stop_target': None},
        separators=(',', ':'), sort_keys=True), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        reason = str(error)
        if isinstance(error, RuntimeError) and re.fullmatch(r'(?:HOLD_)?[A-Z0-9_]{1,96}', reason):
            reason = reason if reason.startswith('HOLD_') else 'HOLD_' + reason
        else:
            reason = 'HOLD_MEMORY_CENSUS_' + type(error).__name__.upper()
        print('NOX_MAINT_MEMORY_BACKGROUND_CENSUS=' + json.dumps(
            {'authority': 'READ_ONLY', 'state': reason, 'stop_target': None},
            separators=(',', ':')), flush=True)
        raise SystemExit(2) from None
