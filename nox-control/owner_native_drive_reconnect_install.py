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
