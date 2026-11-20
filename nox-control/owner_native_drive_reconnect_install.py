#!/usr/bin/env python3
"""Exactly scoped owner-native NOX Drive reconnect installer on Vast #60509551.

The source bundle is injected by the verified Github owner maintenance pipeline.
No token, auth, browser or other NOX service is modified or restarted.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import stat

SCHEMA = 'NOX_OWNER_DRIVE_RECONNECT_INSTALL_V1'
EXPECTED = {'nox_drive_reconnect.py','nox_drive_reconnect_loop.sh','nox_drive_first.py','nox_drive_prefetch.py','nox_drive_native_binding.py','nox-drive-first.skill.md','nox-drive-reconnect.conf'}
BUNDLE = __NOX_BUNDLE_JSON__
ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'ops/drive-auth'
STATE = Path('/var/lib/nox-drive-reconnect')
DRIVE_FIRST_STATE = Path('/var/lib/nox-drive-first')
SUPERVISOR_DIR = Path('/etc/supervisor/conf.d')
CONFIG = Path('/root/.config/rclone/rclone.conf')


class Hold(Exception):
    pass


def require(ok, code):
    if not ok:
        raise Hold('HOLD_DRIVE_RECONNECT_' + code)


def private_dir(path, create=False):
    require(path.is_absolute() and not path.is_symlink() and not any(p.is_symlink() for p in path.parents), 'DIR_LINK')
    if create and not path.exists():
        path.mkdir(mode=0o700,parents=True,exist_ok=False)
    require(path.is_dir() and path.stat().st_uid==os.geteuid(), 'DIR_OWNER')
    require(not path.stat().st_mode & 0o022, 'DIR_PERMISSIONS')
    return path


def decode_bundle(bundle):
    require(isinstance(bundle,dict) and set(bundle)==EXPECTED, 'BUNDLE_SHAPE')
    files={}
    for name,row in bundle.items():
        require(isinstance(row,dict) and set(row)=={'content','sha256'}, 'BUNDLE_ITEM')
        require(isinstance(row['content'],str) and isinstance(row['sha256'],str) and re.fullmatch('[0-9a-f]{64}',row['sha256']), 'BUNDLE_SHA')
        try: raw=base64.b64decode(row['content'],validate=True)
        except (ValueError,TypeError): raise Hold('HOLD_DRIVE_RECONNECT_BUNDLE_BASE64') from None
        require(0 < len(raw) <= 65536 and hashlib.sha256(raw).hexdigest()==row['sha256'], 'BUNDLE_HASH')
        files[name]=raw
    require(files['nox_drive_reconnect.py'].startswith(b'#!/usr/bin/env python3'), 'PY_SOURCE')
    require(files['nox_drive_first.py'].startswith(b'#!/usr/bin/env python3'), 'DRIVE_FIRST_SOURCE')
    require(files['nox_drive_prefetch.py'].startswith(b'#!/usr/bin/env python3'), 'PREFETCH_SOURCE')
    require(files['nox_drive_native_binding.py'].startswith(b'#!/usr/bin/env python3'), 'NATIVE_BINDING_SOURCE')
    require(b'NOX Drive-first skill' in files['nox-drive-first.skill.md'], 'SKILL_SOURCE')
    require(files['nox_drive_reconnect_loop.sh'].startswith(b'#!/bin/sh'), 'SHELL_SOURCE')
    require(b'[program:nox-drive-reconnect]' in files['nox-drive-reconnect.conf'], 'SUPERVISOR_SOURCE')
    return files


def atomic_install(path, raw):
    require(path.is_absolute() and not path.is_symlink(), 'DEST_LINK')
    if path.exists():
        require(path.is_file() and path.stat().st_uid==os.geteuid() and path.stat().st_nlink==1, 'DEST_TYPE')
        old=path.read_bytes()
        if old==raw: return 'ALREADY_CURRENT'
        # Never discard an older reviewed file: one stable, content-addressed backup.
        backup=path.with_name('.'+path.name+'.previous-'+hashlib.sha256(old).hexdigest()[:16])
        if backup.exists(): require(backup.is_file() and backup.read_bytes()==old,'BACKUP_CONFLICT')
        else:
            with backup.open('xb') as out:
                out.write(old);out.flush();os.fsync(out.fileno())
            backup.chmod(0o600)
    temp=path.with_name('.'+path.name+'.nox-stage')
    require(not temp.exists() and not temp.is_symlink(), 'TEMP_EXISTS')
    try:
        fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
        path.chmod(0o600)
        require(hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(raw).digest(), 'READBACK')
        return 'INSTALLED_VERIFIED'
    finally:
        temp.unlink(missing_ok=True)




# A single owner-authorized dispatcher-only activation, not a new daemon or queue.
# The serving model, proxy, web, S03, GPU and all weights are never restarted.
DISPATCHER_SOURCE = ROOT / "scripts/nox_dispatcher_t855u.py"
STAGED_DISPATCHER_SHA = "c9d08cbcd6afe91259129a154b31038ebacd50f648e027eac9fa89a2094f5649"
DISPATCHER_NAME = "nox-dispatcher-t855u"
WORKER_STATUS = ROOT / "status/agents_t856u.json"
NATIVE_QUEUE = ROOT / "state/dispatcher/state.json"
ACTIVATION_STOPS = (
    "/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP",
    "/root/nox/state/OWNER_MAINTENANCE.flag", "/workspace/NOX_STOP",
    "/root/nox/state/DRIVE_STOP.flag"
)
NOX_SERVING = ("nox-ds41-8098", "nox-proxy", "nox-web29-18775")


def _private_json(path, bound):
    require(path.is_absolute() and not path.is_symlink()
            and not any(p.is_symlink() for p in path.parents), "LIVE_JSON_LINK")
    st = path.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()
            and not (st.st_mode & 0o022)
            and 0 < st.st_size <= bound, "LIVE_JSON_PERMS")
    raw = path.read_bytes()
    require(len(raw) == st.st_size, "LIVE_JSON_DRIFT")
    doc = json.loads(raw)
    require(isinstance(doc, dict), "LIVE_JSON_SHAPE")
    return doc


def _supervisor_pid(name):
    p = subprocess.run(["supervisorctl", "status", name],
                       capture_output=True, timeout=8, check=False)
    if p.returncode:
        return None
    match = re.search(rb"^" + name.encode() + rb"\s+RUNNING\s+pid\s+([0-9]+),",
                      p.stdout.strip())
    return int(match.group(1)) if match else None


def _process_started_at(pid):
    try:
        proc = (Path("/proc") / str(pid) / "stat").read_text()
        ticks = int(proc.rsplit(")", 1)[1].split()[19])
        stat_text = Path("/proc/stat").read_text()
        boot = int(next(s.split()[1] for s in stat_text.splitlines()
                        if s.startswith("btime ")))
        hz = os.sysconf("SC_CLK_TCK")
        return boot + ticks / hz if hz > 0 else None
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def _native_idle_sample():
    require(not any(os.path.lexists(x) for x in ACTIVATION_STOPS),
            "ACTIVATION_STOP")
    state = _private_json(NATIVE_QUEUE, 32 * 1024 * 1024)
    tasks = state.get("tasks")
    require(isinstance(tasks, dict) and len(tasks) <= 5000,
            "ACTIVATION_QUEUE_SHAPE")
    require(all(isinstance(v, dict) and v.get("status") not in (
        "running", "claimed", "executing", "in_progress")
        for v in tasks.values()), "ACTIVATION_ACTIVE_TASK")
    status = _private_json(WORKER_STATUS, 2 * 1024 * 1024)
    native = status.get("native_subexecutors")
    require(isinstance(native, dict), "ACTIVATION_NATIVE_STATUS")
    director = native.get("director")
    workers = native.get("workers")
    require(isinstance(director, dict) and isinstance(workers, list)
            and len(workers) == 3, "ACTIVATION_WORKERS")
    pid = director.get("pid")
    require(type(pid) is int and pid > 0 and pid == _supervisor_pid(DISPATCHER_NAME),
            "ACTIVATION_DIRECTOR")
    require(isinstance(native.get("observed_at"), (float, int))
            and abs(time.time() - native["observed_at"]) < 80,
            "ACTIVATION_STATUS_STALE")
    pids = []
    for row in workers:
        require(isinstance(row, dict) and row.get("current_task") is None
                and row.get("state") == "RUNNING"
                and type(row.get("pid")) is int and row["pid"] > 0,
                "ACTIVATION_WORKER_BUSY")
        pids.append(row["pid"])
    require(len(set(pids + [pid])) == 4, "ACTIVATION_PID_DUPLICATE")
    return {"pid": pid, "workers": pids, "tasks": len(tasks)}


def _reclaimable_restart_admission():
    """A small like-for-like process restart, NOT weight transfer admission."""
    mem = Path("/sys/fs/cgroup")
    maximum = (mem / "memory.max").read_text().strip()
    used = int((mem / "memory.current").read_text().strip())
    require(maximum.isdecimal() and int(maximum) > used, "ACTIVATION_CGROUP")
    raw_free = int(maximum) - used
    entries = {}
    for line in (mem / "memory.stat").read_text().splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] in ("inactive_file", "anon", "shmem"):
            entries[fields[0]] = int(fields[1])
    events = {}
    for line in (mem / "memory.events").read_text().splitlines():
        fields = line.split()
        if len(fields) == 2:
            events[fields[0]] = int(fields[1])
    pressure = (mem / "memory.pressure").read_text().splitlines()
    m = re.search(r"\bavg10=([0-9.]+)", pressure[0] if pressure else "")
    require(m is not None, "ACTIVATION_PRESSURE_UNKNOWN")
    # Only 3 existing, idle CPU workers are being replaced. Keep 64MiB raw
    # reserve plus >16GiB inactive file cache, zero OOM kills and low PSI.
    # This does NOT lower the 384MiB raw gate for any Drive transfer.
    allowed = (raw_free >= 64 * 1024**2
               and entries.get("inactive_file", 0) >= 16 * 1024**3
               and int(maximum) - (used - entries.get("inactive_file", 0)) >= 8 * 1024**3
               and events.get("oom_kill") == 0
               and events.get("oom") == 0
               and float(m.group(1)) <= 0.05)
    return {"allowed": allowed, "raw_free_bytes": raw_free,
            "inactive_file_bytes": entries.get("inactive_file", 0),
            "psi_some_avg10": float(m.group(1))}


def _safe_dispatcher_group_stop():
    """Never stop a director unless Supervisor also owns its worker group."""
    import configparser
    base = Path("/etc/supervisor/conf.d")
    try:
        configs = sorted(base.glob("*.conf"))
        if len(configs) > 120:
            return False
        for file in configs:
            if file.is_symlink() or not file.is_file() or file.stat().st_size > 65536:
                continue
            cp = configparser.RawConfigParser(interpolation=None, strict=False)
            cp.read_string(file.read_text(encoding="utf-8"))
            section = "program:" + DISPATCHER_NAME
            if cp.has_section(section):
                return (cp.getboolean(section, "stopasgroup", fallback=False)
                        and cp.getboolean(section, "killasgroup", fallback=False))
    except (OSError, UnicodeError, ValueError, configparser.Error):
        return False
    return False


def activate_staged_dispatcher():
    """Safe single restart after two fresh owner/queue/STOP/cgroup checks."""
    source = DISPATCHER_SOURCE
    require(source.is_file() and not source.is_symlink(),
            "ACTIVATION_SOURCE")
    raw = source.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == STAGED_DISPATCHER_SHA
            and b"NOX_DRIVE_FIRST_STATIC_V1_START" in raw
            and b"NOX_DRIVE_FIRST_STATIC_V1_END" in raw,
            "ACTIVATION_SOURCE_SHA")
    source_mtime = source.stat().st_mtime_ns / 1e9
    serving = {n: _supervisor_pid(n) for n in NOX_SERVING}
    require(all(isinstance(p, int) and p > 0 for p in serving.values()),
            "ACTIVATION_SERVING")
    first = _native_idle_sample()
    if (_process_started_at(first["pid"]) or 0) >= source_mtime:
        return {"state": "SOURCE_LOADED_AFTER_STAGE_INFERRED",
                "dispatcher_restarted": False,
                "live_registration_receipt": False,
                "current_pid": first["pid"],
                "serving_pids_preserved": True}
    admission = _reclaimable_restart_admission()
    if not admission["allowed"]:
        return {"state": "DEFERRED_DISPATCHER_RESTART_RESOURCES",
                "dispatcher_restarted": False,
                "live_registration_receipt": False,
                "raw_free_bytes": admission["raw_free_bytes"],
                "inactive_file_bytes": admission["inactive_file_bytes"]}
    if not _safe_dispatcher_group_stop():
        return {"state": "DEFERRED_GROUP_STOP_UNVERIFIED",
                "dispatcher_restarted": False, "live_registration_receipt": False}
    time.sleep(1)
    second = _native_idle_sample()
    require(first == second, "ACTIVATION_QUEUE_CHANGED")
    require(_reclaimable_restart_admission()["allowed"], "ACTIVATION_RESOURCE_CHANGED")
    require(not any(os.path.lexists(x) for x in ACTIVATION_STOPS),
            "ACTIVATION_STOP_CHANGED")
    stop = subprocess.run(["supervisorctl", "stop", DISPATCHER_NAME],
                          capture_output=True, timeout=35, check=False)
    require(stop.returncode == 0, "DISPATCHER_STOP_FAILED")
    former = [first["pid"]] + first["workers"]
    for _ in range(16):
        if not any((Path("/proc") / str(pid)).exists() for pid in former):
            break
        time.sleep(1)
    # Never start a second live dispatcher while old worker processes remain.
    require(not any((Path("/proc") / str(pid)).exists() for pid in former),
            "OLD_WORKERS_STILL_ALIVE")
    require(not any(os.path.lexists(x) for x in ACTIVATION_STOPS),
            "ACTIVATION_STOP_AFTER_STOP")
    require(hashlib.sha256(source.read_bytes()).hexdigest() == STAGED_DISPATCHER_SHA,
            "ACTIVATION_SOURCE_CHANGED")
    started = subprocess.run(["supervisorctl", "start", DISPATCHER_NAME],
                             capture_output=True, timeout=35, check=False)
    require(started.returncode == 0, "DISPATCHER_START_FAILED")
    # A service RUNNING alone is not enough: demand a newer PID and 3 workers.
    for _ in range(30):
        time.sleep(2)
        pid = _supervisor_pid(DISPATCHER_NAME)
        if (not pid or pid == first["pid"] or
                (_process_started_at(pid) or 0) < source_mtime):
            continue
        try:
            sample = _native_idle_sample()
        except (OSError, ValueError, Hold):
            continue
        if sample["pid"] != pid or len(sample["workers"]) != 3:
            continue
        if {n: _supervisor_pid(n) for n in NOX_SERVING} != serving:
            return {"state": "HOLD_SERVING_IDENTITY_CHANGED",
                    "dispatcher_restarted": True,
                    "live_registration_receipt": False}
        return {"state": "DISPATCHER_RELOADED_THREE_WORKERS",
                "dispatcher_restarted": True,
                "live_registration_receipt": False,
                "new_pid": pid, "old_pid": first["pid"],
                "serving_pids_preserved": True,
                "source_sha256": STAGED_DISPATCHER_SHA}
    return {"state": "HOLD_DISPATCHER_WORKER_READBACK",
            "dispatcher_restarted": True,
            "live_registration_receipt": False}


def install():
    require(os.geteuid()==0, 'OWNER_UID')
    require(re.fullmatch('[0-9a-f]{40}',os.environ.get('NOX_OWNER_SOURCE_SHA','')) is not None, 'SOURCE_PIN')
    require(re.fullmatch('[1-9][0-9]{0,23}',os.environ.get('NOX_OWNER_REQUEST_ID','')) is not None, 'OWNER_REQUEST')
    # No mutation if the owner has stopped or locked NOX.
    for value in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/state/STOP','/root/nox/state/OWNER_MAINTENANCE.flag','/workspace/NOX_STOP'):
        require(not os.path.lexists(value), 'OWNER_STOP')
    assets=decode_bundle(BUNDLE)
    private_dir(ROOT)
    private_dir(ROOT/'ops',create=True)
    private_dir(SCRIPTS,create=True)
    private_dir(STATE,create=True)
    private_dir(DRIVE_FIRST_STATE,create=True)
    stages={}
    for name in ('nox_drive_reconnect.py','nox_drive_reconnect_loop.sh','nox_drive_first.py','nox_drive_prefetch.py','nox_drive_native_binding.py'):
        stages[name]=atomic_install(SCRIPTS/name,assets[name])
    private_dir(SCRIPTS/'skills',create=True)
    stages['nox-drive-first.skill.md']=atomic_install(SCRIPTS/'skills/nox-drive-first.skill.md',assets['nox-drive-first.skill.md'])
    # Never change permissions of preexisting shared NOX directories.
    # Dedicated subdirectories inherit the already verified private owner roots.
    private_dir(SCRIPTS/'private',create=True)
    private_dir(SCRIPTS/'private/drive-tasks',create=True)
    private_dir(STATE/'cache',create=True)
    private_dir(STATE/'cache/warm-ssd',create=True)
    # Source staging is part of this existing authenticated owner transaction.
    # The running dispatcher / three native workers are NEVER restarted here.
    sys.path.insert(0,str(SCRIPTS))
    try:
        from nox_drive_native_binding import stage_native_dispatcher_source
        registry=stage_native_dispatcher_source(
            expected_bridge_sha=hashlib.sha256(assets['nox_drive_native_binding.py']).hexdigest())
    except Exception as exc:
        raise Hold('HOLD_DRIVE_RECONNECT_REGISTRY_STAGE_'+type(exc).__name__.upper()) from None
    require(isinstance(registry,dict) and registry.get('state') in (
        'SOURCE_STAGED_NOT_LIVE','ALREADY_STAGED_NOT_LIVE')
        and registry.get('native_handler_registered') is False
        and registry.get('restarted') is False, 'REGISTRY_STAGE_RECEIPT')
    stages['dispatcher_registry_source']=registry['state']
    activation = activate_staged_dispatcher()
    monitor='MONITOR_NOT_CONFIGURED'
    if SUPERVISOR_DIR.is_dir() and shutil.which('supervisorctl'):
        # Only this new program is updated. Do not restart the dispatcher, chat or S03.
        path=SUPERVISOR_DIR/'nox-drive-reconnect.conf'
        stages['supervisor']=atomic_install(path,assets['nox-drive-reconnect.conf'])
        reread=subprocess.run(['supervisorctl','reread'],capture_output=True,timeout=15,check=False)
        if reread.returncode==0:
            update=subprocess.run(['supervisorctl','update','nox-drive-reconnect'],capture_output=True,timeout=20,check=False)
            if update.returncode==0:
                status=subprocess.run(['supervisorctl','status','nox-drive-reconnect'],capture_output=True,timeout=10,check=False)
                if status.returncode==0 and b'RUNNING' in status.stdout:
                    monitor='SUPERVISOR_RUNNING'
                else: monitor='SUPERVISOR_STATUS_UNCONFIRMED'
            else: monitor='SUPERVISOR_UPDATE_FAILED'
        else: monitor='SUPERVISOR_REREAD_FAILED'
    result={'schema':SCHEMA,'instance_id':60509551,'state':'SOURCE_INSTALLED_MONITOR_'+monitor,
            'monitor':monitor,'source_sha256':os.environ['NOX_OWNER_SOURCE_SHA'],
            'script_sha256':hashlib.sha256(assets['nox_drive_reconnect.py']).hexdigest(),
            'stages':stages,'drive_first_source_installed':True,
            'native_drive_binding_source_installed':True,
            'native_dispatcher_handler_registered':False,
            'dispatcher_source_staged':True,
            'dispatcher_staged_sha256':registry['new_sha256'],
            'dispatcher_activation':activation,
            'dispatcher_only_restarted':activation.get('dispatcher_restarted',False),
            'dispatcher_source_reloaded':activation['state'] in (
                'DISPATCHER_RELOADED_THREE_WORKERS',
                'SOURCE_LOADED_AFTER_STAGE_INFERRED'),
            'dispatcher_source_backup_sha256':registry.get('backup_sha256'),
            'google_oauth_ready':False,'google_read_connected':False,
            'google_write_tested':False,'active_model_restarted':False,
            'other_services_restarted':False,'s03_modified':False,'weights_modified':False}
    # Do not infer Google OAuth from source or monitor status.
    print('NOX_MAINT_DRIVE_RECONNECT_INSTALL='+json.dumps(result,sort_keys=True),flush=True)
    print('NOX_MAINT_DRIVE_RECONNECT_INSTALL_COMPLETE=true',flush=True)
    return 0


def main():
    try: return install()
    except Hold as err:
        print('NOX_MAINT_DRIVE_RECONNECT_INSTALL_HOLD='+str(err),flush=True)
        return 2
    except Exception as exc:
        print('NOX_MAINT_DRIVE_RECONNECT_INSTALL_HOLD=HOLD_DRIVE_RECONNECT_'+type(exc).__name__.upper(),flush=True)
        return 2

if __name__=='__main__':raise SystemExit(main())
