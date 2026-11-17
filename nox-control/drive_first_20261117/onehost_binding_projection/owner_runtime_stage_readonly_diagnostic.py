#!/usr/bin/env python3
"""Fixed-path metadata/hash diagnostic. No chmod, locks, imports of runtime, or writes."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/root/nox')
PROC = Path('/proc')
MAX_PROC_LOCKS_BYTES = 256 * 1024
MAX_PROC_LOCK_ROWS = 4096
MAX_HOLDER_PIDS = 8
DEST_NAME = 'drive_first_20261117_ee142b97c813'
BUNDLE_SHA256 = 'ee142b97c81327edf0130e2aba46c431e1d1334396581b11922507310553aa2b'
STAGING_MANIFEST_SHA256 = '61433567b16a2bd5433104146fad458a7f1427b6a7159a948211227b349a1d9d'
EXPECTED = {
    'runtime/nox_integrations/__init__.py': (364, '13fa6a78def2edfb4b9ff819f36e933aabd4b17c0a3196f0d77ccb5f27841be9'),
    'runtime/nox_integrations/__main__.py': (1368, '14ae1e9c9fe3dd0477d1809489177846f48a3bdc8cb2dbc89ad046b0fde88bd2'),
    'runtime/nox_integrations/config.py': (5394, '29682a5e43ce4485ee9d91d3001800a27159df5c890083c06a5296a575468cc8'),
    'runtime/nox_integrations/core.py': (7028, 'c660e389cd2c6318aacc4468a2cfa2198640b5fb2510b2b20d9b035479e480db'),
    'runtime/nox_integrations/drive.py': (19308, '2d985e33ed6501b95a085b85abbf5654d576513b9570710f706e678e8ff78c3b'),
    'runtime/nox_integrations/host.py': (6782, '5130d9028d60a9f78f5c0b3644c067329219f98d389859b1fdd6d933f946da1d'),
    'runtime/nox_integrations/memfd.py': (5877, 'ec9910a67228cc8681a1f1157f9107003bac4634548ec3130bc43573745b1386'),
    'runtime/nox_integrations/providers.py': (4512, '329d036498b6c38af71b996f15c138b5efbdc0a7d64f3c919f61745bfe8acebe'),
    'runtime/nox_warm/__init__.py': (213, '696685fce0e046b6f53bfd2e3c866cdafbb8a16086faa00290f7fdcb94a156f2'),
    'runtime/nox_warm/__main__.py': (2795, 'ee9991fcbacaec2cc8bc720dcebfa7f13aae0f2ddb0963b55a84899957cf214c'),
    'runtime/nox_warm/cache.py': (6803, '48bd8b61c002235ad6e7365bda9f80a21810fd98c05d5fba5ca169b9b055e9e5'),
    'runtime/nox_warm/controller.py': (37941, '1312845745150bbfc52863fa6eab85d67da12d5108fb1cc1a7776d56621b5d05'),
}


class ProbeIssue(Exception):
    def __init__(self, code, component):
        self.code, self.component = code, str(component)


def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)


def metadata(s):
    kind = ('directory' if stat.S_ISDIR(s.st_mode) else 'regular' if stat.S_ISREG(s.st_mode)
            else 'symlink' if stat.S_ISLNK(s.st_mode) else 'other')
    return {'type': kind, 'uid': s.st_uid, 'gid': s.st_gid,
            'mode': format(stat.S_IMODE(s.st_mode), '04o'), 'size': s.st_size,
            'dev': s.st_dev, 'inode': s.st_ino, 'nlink': s.st_nlink,
            'owner_matches_euid': s.st_uid == os.geteuid(),
            'group_or_other_writable': bool(s.st_mode & 0o022)}


def parent_fd(path):
    """Open only the fixed path's ancestors, rejecting every symlink component."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ProbeIssue('INVALID_FIXED_PATH', path)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    prefix = Path('/')
    try:
        for part in path.parts[1:-1]:
            prefix = prefix / part
            before = os.stat(part, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise ProbeIssue('SYMLINK_ANCESTOR' if stat.S_ISLNK(before.st_mode) else 'NON_DIRECTORY_ANCESTOR', prefix)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            if (before.st_dev, before.st_ino) != (os.fstat(child).st_dev, os.fstat(child).st_ino):
                os.close(child)
                raise ProbeIssue('ANCESTOR_CHANGED', prefix)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def inspect(path, *, expected=None, flag=False, deadline=None):
    row = {'path': str(path), 'exists': None, 'bytes_read': 0}
    if expected is not None:
        row.update(expected_bytes=expected[0], expected_sha256=expected[1], sha256=None, matches_manifest=False)
    if flag:
        row.update(value=None, value_scope='Only literal 0 or 1 is returned; other contents withheld')
    parent = fd = None
    try:
        parent = parent_fd(path)
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        row.update(exists=True, metadata=metadata(before), status='METADATA_ONLY')
        if expected is None and not flag:
            row['stage_directory_guard_ok'] = (stat.S_ISDIR(before.st_mode)
                and before.st_uid == os.geteuid() and not before.st_mode & 0o022)
            return row
        if not stat.S_ISREG(before.st_mode):
            row['status'] = 'NOT_REGULAR_NO_READ'
            return row
        maximum = 32 if flag else expected[0]
        if before.st_size > maximum or (expected is not None and before.st_size != maximum):
            row['status'] = 'SIZE_MISMATCH_NO_READ'
            return row
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if identity(before) != identity(os.fstat(fd)):
            row['status'] = 'CHANGED_BEFORE_READ'
            return row
        chunks = []
        while row['bytes_read'] <= maximum:
            if deadline is not None and time.monotonic() > deadline:
                row['status'] = 'DEADLINE'
                return row
            chunk = os.read(fd, min(65536, maximum + 1 - row['bytes_read']))
            if not chunk:
                break
            chunks.append(chunk)
            row['bytes_read'] += len(chunk)
        after = os.fstat(fd)
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if identity(before) != identity(after) or identity(after) != identity(current):
            row['status'] = 'CHANGED_DURING_READ'
            return row
        value = b''.join(chunks)
        if len(value) != before.st_size:
            row['status'] = 'READ_SIZE_CHANGED'
            return row
        if flag:
            row['value'] = int(value.strip()) if value.strip() in (b'0', b'1') else None
            row['status'] = 'FLAG_OBSERVED' if row['value'] is not None else 'FLAG_UNKNOWN_CONTENT_WITHHELD'
            row['would_pass_original_owner_idle_file_guard'] = bool(row['value'] == 0
                and before.st_uid == os.geteuid() and not before.st_mode & 0o022)
        else:
            row['sha256'] = hashlib.sha256(value).hexdigest()
            row['matches_manifest'] = row['sha256'] == expected[1]
            row['would_pass_original_stage_file_guard'] = bool(row['matches_manifest']
                and before.st_uid == os.geteuid() and not before.st_mode & 0o022)
            row['status'] = 'SOURCE_HASH_MATCH' if row['matches_manifest'] else 'SOURCE_HASH_MISMATCH'
        return row
    except FileNotFoundError:
        row.update(status='PATH_OR_ANCESTOR_MISSING', exists=False)
    except ProbeIssue as issue:
        row.update(status=issue.code, obstructing_component=issue.component)
    except OSError as error:
        row.update(status='OS_ERROR_METADATA_ONLY', errno=error.errno)
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)
    return row


def read_proc_bounded(path, maximum, deadline):
    """Only /proc/locks or a matched holder's stat/status; return no raw text in receipts."""
    parent = fd = None
    try:
        parent = parent_fd(path)
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise ProbeIssue('PROC_NOT_REGULAR', path)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        proc_identity = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid)
        if proc_identity(before) != proc_identity(os.fstat(fd)):
            raise ProbeIssue('PROC_CHANGED_BEFORE_READ', path)
        pieces = []
        total = 0
        while total <= maximum:
            if time.monotonic() > deadline:
                raise ProbeIssue('PROC_DEADLINE', path)
            part = os.read(fd, min(65536, maximum + 1 - total))
            if not part:
                break
            pieces.append(part)
            total += len(part)
        after = os.fstat(fd)
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if proc_identity(before) != proc_identity(after) or proc_identity(after) != proc_identity(current):
            raise ProbeIssue('PROC_IDENTITY_CHANGED', path)
        if total > maximum:
            raise ProbeIssue('PROC_TRUNCATED', path)
        return b''.join(pieces)
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)


def parse_lock_matches(raw, dev, inode):
    lines = raw.splitlines()
    if len(lines) > MAX_PROC_LOCK_ROWS:
        raise ProbeIssue('PROC_LOCK_ROW_LIMIT', PROC/'locks')
    matches = []
    for line in lines:
        if not line.strip():
            continue
        if len(line) > 512:
            raise ProbeIssue('PROC_LOCK_LINE_LIMIT', PROC/'locks')
        parts = line.split()
        waiter = len(parts) > 1 and parts[1] == b'->'
        if waiter:
            parts = parts[:1] + parts[2:]
        if (len(parts) != 8 or not re.fullmatch(rb'[0-9]+:', parts[0])
                or not re.fullmatch(rb'[A-Z_]+', parts[1])
                or not re.fullmatch(rb'[A-Z_]+', parts[2])
                or not re.fullmatch(rb'[A-Z_]+', parts[3])
                or not re.fullmatch(rb'-?[0-9]{1,10}', parts[4])):
            raise ProbeIssue('PROC_LOCK_FORMAT_UNKNOWN', PROC/'locks')
        address = re.fullmatch(rb'([0-9a-fA-F]+):([0-9a-fA-F]+):([0-9]+)', parts[5])
        if not address or not all(re.fullmatch(rb'[0-9]+|EOF', x) for x in parts[6:]):
            raise ProbeIssue('PROC_LOCK_ADDRESS_UNKNOWN', PROC/'locks')
        major, minor, observed_inode = int(address[1],16), int(address[2],16), int(address[3])
        if (major,minor,observed_inode) != (os.major(dev),os.minor(dev),inode):
            continue
        pid = int(parts[4])
        if pid < -1 or pid > 2**31-1:
            raise ProbeIssue('PROC_LOCK_PID_UNKNOWN', PROC/'locks')
        matches.append({'class':parts[1].decode('ascii'), 'advisory':parts[2].decode('ascii'),
            'mode':parts[3].decode('ascii'), 'pid':pid, 'waiter':waiter,
            'dev_major':major, 'dev_minor':minor, 'inode':observed_inode,
            'start':parts[6].decode('ascii'), 'end':parts[7].decode('ascii')})
    return sorted(matches,key=lambda r:(r['waiter'],r['pid'],r['class'],r['mode'],r['start'],r['end']))


def proc_start_ticks(raw, pid):
    close = raw.rfind(b')')
    opening = raw.find(b'(')
    if opening < 1 or close <= opening or raw[:opening].strip() != str(pid).encode():
        raise ProbeIssue('PROC_STAT_PID_FORMAT', PROC/str(pid)/'stat')
    fields = raw[close+1:].split()
    if len(fields) < 20 or not re.fullmatch(rb'[0-9]{1,20}',fields[19]):
        raise ProbeIssue('PROC_STAT_START_TICKS_UNKNOWN', PROC/str(pid)/'stat')
    return int(fields[19])


def holder_metadata(pid, deadline):
    start = proc_start_ticks(read_proc_bounded(PROC/str(pid)/'stat',8192,deadline),pid)
    raw = read_proc_bounded(PROC/str(pid)/'status',65536,deadline)
    selected = {}
    for line in raw.splitlines():
        key,sep,value = line.partition(b':')
        if sep and key in (b'Name',b'Uid',b'Gid'):
            if key in selected:
                raise ProbeIssue('PROC_STATUS_DUPLICATE_FIELD', PROC/str(pid)/'status')
            selected[key]=value.strip()
    if set(selected) != {b'Name',b'Uid',b'Gid'}:
        raise ProbeIssue('PROC_STATUS_FIELDS_MISSING', PROC/str(pid)/'status')
    ids={}
    for key in (b'Uid',b'Gid'):
        values=selected[key].split()
        if len(values)!=4 or not all(re.fullmatch(rb'[0-9]{1,10}',v) for v in values):
            raise ProbeIssue('PROC_STATUS_IDS_UNKNOWN', PROC/str(pid)/'status')
        ids[key.decode('ascii').lower()]=[int(v) for v in values]
    end = proc_start_ticks(read_proc_bounded(PROC/str(pid)/'stat',8192,deadline),pid)
    if end != start:
        raise ProbeIssue('PROC_PID_REUSED_OR_CHANGED', PROC/str(pid)/'stat')
    name=''.join(chr(c) for c in selected[b'Name'] if 32<=c<127)[:64]
    return {'pid':pid,'start_ticks':start,'identity_stable_across_status_read':True,
            'name':name,'uid':ids['uid'],'gid':ids['gid'],'cmdline_read':False,'environment_read':False}


def maintenance_snapshot(deadline):
    path=ROOT/'state/owner_maintenance.lock'
    first=inspect(path)
    result={'state':'UNKNOWN','metadata_before':first,'matching_locks':[], 'holders':[],
            'locks_acquired':0,'unlock_calls':0,'kill_calls':0,
            'free_lock_proven':False,'retry_authorized':False,
            'visibility_scope':'Current /proc mount and PID namespace; point-in-time observation only'}
    meta=first.get('metadata',{})
    if meta.get('type')!='regular':
        result['reason']='MAINTENANCE_LOCK_NOT_REGULAR_OR_UNAVAILABLE'
        return result
    try:
        raw=read_proc_bounded(PROC/'locks',MAX_PROC_LOCKS_BYTES,deadline)
        rows=parse_lock_matches(raw,meta['dev'],meta['inode'])
        result['matching_locks']=rows
        result['proc_locks_bytes_before']=len(raw)
        owners=[r for r in rows if not r['waiter']]
        if any(r['class']=='OFDLCK' or r['pid']<=0 for r in owners):
            result['reason']='OFD_OR_UNRESOLVED_HOLDER_PID'
            return result
        pids=sorted({r['pid'] for r in owners})
        if len(pids)>MAX_HOLDER_PIDS:
            result['reason']='HOLDER_PID_LIMIT'
            return result
        # Blocked (->) entries are waiters and never authorize /proc/PID reads.
        result['holders']=[holder_metadata(pid,deadline) for pid in pids]
        raw_after=read_proc_bounded(PROC/'locks',MAX_PROC_LOCKS_BYTES,deadline)
        rows_after=parse_lock_matches(raw_after,meta['dev'],meta['inode'])
        result['proc_locks_bytes_after']=len(raw_after)
        result['matching_locks_after']=rows_after
        last=inspect(path);result['metadata_after']=last
        if last.get('metadata')!=meta or rows_after!=rows:
            result['reason']='LOCK_SNAPSHOT_CHANGED'
            return result
        if not owners and rows:
            result['reason']='WAITERS_WITHOUT_CONFIRMED_HOLDER'
            return result
        result['state']='HELD_OBSERVED' if owners else 'NO_MATCH_OBSERVED'
        result['reason']='Exact dev/inode matched; positive holder metadata observed' if owners else 'No matching kernel lock in two complete bounded snapshots; existing lease gate still required'
        return result
    except ProbeIssue as issue:
        result['reason']=issue.code
        result['proc_truncated']=issue.code in ('PROC_TRUNCATED','PROC_LOCK_ROW_LIMIT','PROC_LOCK_LINE_LIMIT')
    except OSError as error:
        result.update(reason='PROC_UNAVAILABLE',errno=error.errno)
    return result


def collect():
    started = time.monotonic()
    deadline = started + 10
    destination = ROOT / 'extensions' / DEST_NAME
    paths = [ROOT / 'state/priority', ROOT / 'state', ROOT / 'extensions', destination,
             destination / 'runtime', destination / 'runtime/nox_integrations', destination / 'runtime/nox_warm']
    actual_final_targets = {str(paths[i]) for i in (0, 1, 5, 6)}
    directories = [inspect(p) for p in paths]
    for row in directories:
        row['used_as_final_directory_by_stage_entry'] = row['path'] in actual_final_targets
    active_before = inspect(ROOT / 'state/priority/CHAT_ACTIVE', flag=True, deadline=deadline)
    files = [inspect(destination / name, expected=pin, deadline=deadline) for name, pin in sorted(EXPECTED.items())]
    maintenance = maintenance_snapshot(deadline)
    active_after = inspect(ROOT / 'state/priority/CHAT_ACTIVE', flag=True, deadline=deadline)
    candidates = [row['path'] for row in directories if row['used_as_final_directory_by_stage_entry']
                  and row.get('metadata', {}).get('type') == 'directory' and row.get('stage_directory_guard_ok') is False]
    matched = sum(row.get('matches_manifest', False) for row in files)
    present = sum(row.get('exists') is True for row in files)
    return {'schema': 'NOX_RUNTIME_STAGE_READONLY_DIAGNOSTIC_V1', 'instructions_version': '0.0.6',
        'status': 'READ_ONLY_DIAGNOSTIC_COMPLETE', 'snapshot_atomic': False,
        'failed_stage': {'run_id': '44149977429', 'job_id': '134275278537', 'comment_id': '6957369880',
            'source_commit': 'c49ee68d34fc9e0890a234fbff48d0c0e4132fe5', 'reported_error': 'HOLD_DIRECTORY_OWNER_OR_MODE'},
        'bundle_sha256': BUNDLE_SHA256, 'staging_manifest_sha256': STAGING_MANIFEST_SHA256,
        'destination': str(destination), 'directories': directories,
        'observed_original_directory_guard_failure_candidates': candidates,
        'original_failure_path_proven': False,
        'chat_active_before': active_before, 'chat_active_after': active_after,
        'maintenance_lock_snapshot':maintenance,
        'chat_flag_values_equal': active_before.get('value') is not None and active_before.get('value') == active_after.get('value'),
        'files': files, 'expected_file_count': 12, 'present_file_count': present, 'matching_source_count': matched,
        'all_expected_source_files_match': matched == 12,
        'partial_destination_state': 'ALL_EXPECTED_SOURCE_FILES_MATCH' if matched == 12 else 'PARTIAL_OR_MISMATCH' if present else 'NO_EXPECTED_FILES_OBSERVED',
        'native_mutations': 0, 'chmod_chown_calls': 0, 'locks_acquired': 0, 'network_requests': 0,
        'runtime_imported': False, 'runtime_bound': False, 'native_staging_accepted': False,
        'source_bytes_read': sum(row['bytes_read'] for row in files),
        'max_source_bytes_read': sum(pin[0]+1 for pin in EXPECTED.values()),
        'elapsed_ms': round((time.monotonic()-started)*1000, 2),
        'interpretation': 'Observed metadata/hash snapshot only. No authority to retry staging, chmod, bind callbacks or infer current owner lease.'}


def run():
    request, source = os.environ.get('NOX_OWNER_REQUEST_ID', ''), os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
        raise RuntimeError('HOLD_OWNER_REQUEST_CONTEXT')
    result = collect()
    result.update(owner_request_id=request, owner_source_sha=source)
    return result


def main():
    complete = False
    try:
        result = run()
        complete = result['status'] == 'READ_ONLY_DIAGNOSTIC_COMPLETE'
    except Exception as error:
        result = {'status': 'HOLD_READONLY_DIAGNOSTIC', 'error_type': type(error).__name__,
                  'native_mutations': 0, 'runtime_bound': False, 'raw_error_exported': False}
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'drive_first_runtime_readonly_reconcile', 'data': result},
          ensure_ascii=False, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(complete).lower(), flush=True)
    return 0 if complete else 2


if __name__ == '__main__':
    raise SystemExit(main())
