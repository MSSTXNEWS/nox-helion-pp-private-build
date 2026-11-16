#!/usr/bin/env python3
"""Read-only mounted-storage and documented Google Drive integration inventory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

ROOT = Path('/root/nox')
SAFE_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
PROFILES = ('/root/nox/state/cold_drive.conf', '/root/.config/rclone/rclone.conf', '/root/nox/rclone.conf')
REMOTE = 'nox_drive:'
FOLDER = '1f6d8mwMtR6Be8xMMiA5EpLZI7B47IS2l'
SENTINEL = 'deepseek_iq2_xxs_manifest.json'
SENTINEL_ID = '1DF1I9UQeDxxeYlRT1_FhvepmHXB7bsrr'


def run(argv, timeout=10, limit=262144):
    try:
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'state': 'HOLD_READ_ONLY_TIMEOUT'}, b''
    except OSError:
        return {'state': 'HOLD_COMMAND_UNAVAILABLE'}, b''
    state = 'OK' if p.returncode == 0 else 'HOLD_COMMAND_EXIT'
    err = p.stderr.lower()
    if any(word in err for word in (b'invalid_grant', b'invalid credentials', b'unauthorized', b'401')):
        state = 'HOLD_DRIVE_AUTH'
    elif any(word in err for word in (b'permission denied', b'insufficient permission', b'403')):
        state = 'HOLD_DRIVE_PERMISSION'
    if len(p.stdout) > limit or len(p.stderr) > limit:
        state = 'HOLD_OUTPUT_LIMIT'
    # Never expose provider stderr, config, environment values or response bodies.
    return {'state': state, 'returncode': p.returncode}, p.stdout if state == 'OK' else b''


def profile_metadata(path):
    p = Path(path)
    row = {'path': str(p), 'contents_read': False}
    if any(q.is_symlink() for q in (*p.parents, p)):
        return dict(row, state='HOLD_PROFILE_SYMLINK')
    try:
        s = p.lstat()
    except OSError:
        return dict(row, state='HOLD_PROFILE_NOT_FOUND')
    good = stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid() and stat.S_IMODE(s.st_mode) == 0o600
    return dict(row, state='PRIVATE_PROFILE_METADATA_VERIFIED' if good else 'HOLD_PROFILE_OWNER_MODE',
                regular=stat.S_ISREG(s.st_mode), owner_uid=s.st_uid, mode=oct(stat.S_IMODE(s.st_mode)))


def mount_rows(raw):
    rows = []
    for line in raw.splitlines()[:512]:
        left, separator, right = line.partition(' - ')
        a, b = left.split(), right.split()
        if not separator or len(a) < 6 or len(b) < 1:
            continue
        # Exclude source and both option strings: network sources/options may contain credentials.
        point = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), a[4])
        if not point.startswith('/') or any(ord(c) < 32 for c in point):
            continue
        rows.append({'mountpoint': point, 'device': a[2], 'fstype': b[0],
                     'read_only': 'ro' in a[5].split(',')})
    return rows


def mounted_storage():
    try:
        raw = Path('/proc/self/mountinfo').read_text()[:262144]
    except OSError:
        return {'state': 'HOLD_MOUNTINFO_UNAVAILABLE'}
    rows = mount_rows(raw)
    skip = {'proc', 'sysfs', 'cgroup', 'cgroup2', 'devpts', 'mqueue', 'securityfs', 'debugfs', 'tracefs', 'pstore'}
    seen, volumes = set(), []
    for row in rows:
        if row['fstype'] in skip or row['mountpoint'] in seen:
            continue
        seen.add(row['mountpoint'])
        if len(volumes) >= 64:
            break
        item = dict(row)
        # statvfs is done by df in a timed subprocess below; remote mounts cannot hang this payload.
        volumes.append(item)
    meta, raw_df = run(['/bin/df', '-B1', '--output=target,fstype,size,used,avail'], timeout=8)
    df_rows = []
    if meta['state'] == 'OK':
        for line in raw_df.decode('utf-8', 'replace').splitlines()[1:257]:
            parts = line.rsplit(None, 4)
            if len(parts) == 5 and all(x.isdigit() for x in parts[2:]):
                df_rows.append({'mountpoint': parts[0], 'fstype': parts[1], 'size_bytes': int(parts[2]),
                                'used_bytes': int(parts[3]), 'available_bytes': int(parts[4])})
    meta_ls, raw_ls = run(['/usr/bin/lsblk', '--json', '--bytes', '--output', 'NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,RO'], timeout=8)
    devices = []
    if meta_ls['state'] == 'OK':
        try:
            source = json.loads(raw_ls).get('blockdevices', [])
            def clean(items, depth=0):
                if not isinstance(items, list) or depth > 6:
                    return []
                out = []
                for x in items[:128]:
                    if not isinstance(x, dict):
                        continue
                    y = {k: x[k] for k in ('name', 'type', 'size', 'fstype', 'mountpoint', 'ro')
                         if k in x and isinstance(x[k], (str, int, bool, type(None)))}
                    if 'children' in x:
                        y['children'] = clean(x['children'], depth + 1)
                    out.append(y)
                return out
            devices = clean(source)
        except (ValueError, TypeError, AttributeError):
            meta_ls = {'state': 'HOLD_BLOCK_METADATA_FORMAT'}
    return {'state': 'READ_ONLY_STORAGE_OBSERVED', 'mounts': volumes, 'mountinfo_rows_seen': len(rows),
            'mount_metadata_limit': 64, 'df': dict(meta, filesystems=df_rows),
            'lsblk': dict(meta_ls, blockdevices=devices), 'dev_fuse_exists': Path('/dev/fuse').exists(),
            'visible_device_is_not_proof_of_allocated_or_mounted_storage': True}


def probe_drive(rclone, config_args, label):
    row = {'profile': label, 'profile_contents_read': False}
    meta, raw = run([rclone, 'listremotes', *config_args], timeout=12, limit=16384)
    names = [x for x in raw.decode('utf-8', 'replace').splitlines()
             if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:', x)]
    row['listremotes'] = dict(meta, names=names[:64])
    if meta['state'] != 'OK':
        return dict(row, state=meta['state'])
    if REMOTE not in names:
        return dict(row, state='HOLD_KNOWN_DRIVE_REMOTE_MISSING')
    common = [*config_args, '--drive-root-folder-id', FOLDER, '--retries', '1', '--low-level-retries', '1',
              '--contimeout', '10s', '--timeout', '15s']
    # Exact-file NewFsSrc works with installed rclone1.53; --stat is not required.
    meta, raw = run([rclone, 'lsjson', REMOTE + SENTINEL, *common], timeout=25, limit=65536)
    listing = dict(meta, sentinel_id_verified=False)
    if meta['state'] == 'OK':
        try:
            values = json.loads(raw)
            values = [values] if isinstance(values, dict) else values
            if not isinstance(values, list) or len(values) > 10:
                raise ValueError('scope')
            listing['objects'] = [{k: x[k] for k in ('Name', 'Path', 'ID', 'Size', 'IsDir') if k in x}
                                  for x in values if isinstance(x, dict)]
            listing['sentinel_id_verified'] = any(x.get('Name') == SENTINEL and x.get('ID') == SENTINEL_ID
                                                   and x.get('IsDir') is False for x in values)
        except (ValueError, TypeError, AttributeError):
            listing['state'] = 'HOLD_DRIVE_METADATA_FORMAT'
    row['known_folder'] = listing
    meta, raw = run([rclone, 'about', REMOTE, '--json', *common], timeout=25, limit=65536)
    quota = dict(meta)
    if meta['state'] == 'OK':
        try:
            q = json.loads(raw)
            quota.update({k: q[k] for k in ('total', 'used', 'free', 'trashed', 'other') if type(q.get(k)) is int})
        except (ValueError, TypeError, AttributeError):
            quota['state'] = 'HOLD_DRIVE_QUOTA_FORMAT'
    row['quota'] = quota
    ready = listing.get('sentinel_id_verified') and quota.get('state') == 'OK'
    return dict(row, state='EXISTING_GOOGLE_DRIVE_READ_ACCESS_VERIFIED' if ready else 'HOLD_DRIVE_ACCESS_NOT_VERIFIED',
                write_access='NOT_EXERCISED', streaming_transfer='NOT_EXERCISED')


def main():
    report = {'schema': 'NOX_STORAGE_INTEGRATION_PREFLIGHT_V1', 'observed_at_epoch': time.time(),
              'source_sha': os.environ.get('NOX_OWNER_SOURCE_SHA'), 'request': os.environ.get('NOX_OWNER_REQUEST_ID'),
              'storage': mounted_storage(), 'profiles': [profile_metadata(p) for p in PROFILES],
              'drive_env_names_present': [n for n in ('RCLONE_CONFIG', 'RCLONE_CONFIG_NOX_DRIVE_TYPE',
                  'RCLONE_CONFIG_NOX_DRIVE_TOKEN', 'RCLONE_CONFIG_NOX_DRIVE_SERVICE_ACCOUNT_FILE') if n in os.environ],
              'services_changed': False, 'credential_contents_inspected_or_emitted': False,
              'configured_client_may_use_existing_credentials': True, 'files_transferred': 0,
              'mounts_changed': False, 'queue_changed': False, 'gpu_or_training_action': False,
              'pc_integration': 'DEFERRED_BY_OWNER_GOOGLE_DRIVE_ONLY'}
    rclone = shutil.which('rclone', path=SAFE_PATH)
    probes = []
    if rclone:
        probes.append(probe_drive(rclone, [], 'existing_default_client_configuration'))
        for row in report['profiles']:
            if row['state'] == 'PRIVATE_PROFILE_METADATA_VERIFIED':
                probes.append(probe_drive(rclone, ['--config', row['path']], row['path']))
    report['drive_probes'] = probes
    report['state'] = ('EXISTING_GOOGLE_DRIVE_READ_ACCESS_VERIFIED' if any(
        x['state'] == 'EXISTING_GOOGLE_DRIVE_READ_ACCESS_VERIFIED' for x in probes)
        else 'HOLD_NO_VERIFIED_EXISTING_GOOGLE_DRIVE_PROFILE')
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'storage_integration_preflight', 'data': report}, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)  # Inspection completed; readiness remains report.state.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
