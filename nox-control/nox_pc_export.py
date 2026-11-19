#!/usr/bin/env python3
"""Bounded NOX backup inventory and verified, inactive-GGUF-only eviction.

Run on the NOX server. Large weights are hashed in place; live SQLite databases
use SQLite's backup API. No credentials are included and no recursive deletion
is implemented. This helper never stops training or changes active weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import sqlite3
import stat
import sys
import tarfile
import tempfile
import time
import zipfile

ROOT = Path('/root/nox')
GIB = 1024 ** 3
SESSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
SKIP_DIRS = {'.git', '.cache', '.venv', 'venv', 'node_modules', '__pycache__',
             'pc_exports', 'pc_shell', '.ssh', 'credentials', 'secrets', 'tmp', 'temp',
             'offload', 'offload_weights', 'wandb', 'hf_cache', 'pip_cache'}
SECRET_NAMES = re.compile(r'(^\.env($|\.)|(^|[_.-])(credential|credentials|secret|secrets|token|tokens|password|private_key|api_key|cookie|cookies)([_.-]|$)|^(id_rsa|id_ed25519|operator_ed25519|pc_shell|rclone\.conf|cold_drive\.conf|cold_pc\.conf|vast_api_key)(?:$|\.))', re.I)
SECRET_TEXT = re.compile(rb'(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|client_secret)[\"\x27\s]*[:=][\"\x27\s]*(?:bearer\s+)?[A-Za-z0-9_./+\-=]{20,}')
TEXT_SUFFIX = {'.json', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.conf', '.txt', '.log', '.py', '.sh', '.ps1', '.md', '.csv', '.tsv'}
BINARY_SUFFIX = {'.gguf', '.safetensors', '.bin', '.pt', '.pth', '.zip', '.gz', '.tar', '.zst', '.parquet', '.arrow', '.npy', '.npz'}


def fail(code):
    raise RuntimeError(code)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def atomic_json(path, obj):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.nox-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or any(ord(c) < 32 for c in value):
        fail('INVALID_RELATIVE_PATH')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or ':' in value:
        fail('INVALID_RELATIVE_PATH')
    # Windows cannot represent these names faithfully. Do not silently rename.
    for part in p.parts:
        if any(c in part for c in '<>"|?*') or part.endswith((' ', '.')):
            fail('WINDOWS_INCOMPATIBLE_PATH')
        if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I):
            fail('WINDOWS_INCOMPATIBLE_PATH')
    return value


def plain_source(root, rel):
    rel = safe_relative(rel)
    path = root / rel
    if root.is_symlink():
        fail('SYMLINK_ROOT')
    probe = root
    for part in PurePosixPath(rel).parts:
        probe = probe / part
        if probe.is_symlink():
            fail('SYMLINK_SOURCE')
    return path


def stage_dir(root, session):
    if not SESSION.fullmatch(session):
        fail('INVALID_SESSION')
    result = plain_source(root, 'state/pc_exports/' + session)
    result.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(result, 0o700)
    return result


def looks_secret(path):
    if SECRET_NAMES.search(path.name) or path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.keystore'}:
        return True
    if path.suffix.lower() not in TEXT_SUFFIX:
        return False
    tail = b''
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            data = tail + block
            if b'-----BEGIN PRIVATE KEY-----' in data or b'-----BEGIN OPENSSH PRIVATE KEY-----' in data or SECRET_TEXT.search(data):
                return True
            tail = data[-1024:]
    return False


def archive_safe(path):
    """Opaque archives are held; known tar/zip members get credential screening."""
    def member_safe(name, source=None):
        parts = PurePosixPath(name).parts
        if any(SECRET_NAMES.search(part) or part == '.ssh' for part in parts):
            return False
        if Path(name).suffix.lower() in {'.pem','.key','.p12','.pfx','.keystore'}:
            return False
        if source is not None and Path(name).suffix.lower() in TEXT_SUFFIX:
            tail = b''
            for block in iter(lambda:source.read(1024*1024), b''):
                data = tail+block
                if SECRET_TEXT.search(data) or b'PRIVATE KEY-----' in data:
                    return False
                tail = data[-1024:]
        return True
    suffixes = ''.join(path.suffixes).lower()
    try:
        if suffixes.endswith('.zip'):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        if not member_safe(member.filename): return False
                    else:
                        with archive.open(member) as source:
                            if not member_safe(member.filename, source): return False
            return True
        if suffixes.endswith(('.tar','.tar.gz','.tgz','.tar.bz2','.tar.xz')):
            with tarfile.open(path, 'r|*') as archive:
                for member in archive:
                    if not member_safe(member.name): return False
                    if member.isfile():
                        source = archive.extractfile(member)
                        with source:
                            if not member_safe(member.name, source): return False
            return True
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile, RuntimeError):
        return False
    # Compressed/unknown containers are not silently advertised as credential-free.
    return not suffixes.endswith(('.gz','.bz2','.xz','.zst','.7z','.rar'))


def sqlite_file(path):
    with path.open('rb') as f:
        return f.read(16) == b'SQLite format 3\x00'


def snapshot_sqlite(source, dest):
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.sqlite-', dir=dest.parent)
    os.close(fd)
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30) as src:
            with sqlite3.connect(temp) as target:
                deadline = time.monotonic() + 900
                def progress(status, remaining, total):
                    if time.monotonic() > deadline:
                        fail('SQLITE_SNAPSHOT_TIMEOUT')
                src.backup(target, pages=2048, progress=progress, sleep=0.1)
                if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    fail('SQLITE_SNAPSHOT_CHECK_FAILED')
        os.replace(temp, dest)
        os.chmod(dest, 0o600)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def copy_snapshot(source, dest):
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    before = identity(source)
    fd, temp = tempfile.mkstemp(prefix='.snapshot-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
            shutil.copyfileobj(inp, out, 1024 * 1024)
            out.flush(); os.fsync(out.fileno())
        if identity(source) != before:
            fail('MUTABLE_FILE_CHANGED_RETRY_NEW_SESSION')
        os.replace(temp, dest)
        os.chmod(dest, 0o600)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def active_paths(root):
    values = [root/'models/current.gguf', root/'state', root/'memory', root/'s03',
              root/'S03', root/'progress_pull_t784u', root/'training', root/'checkpoints',
              root/'lora', root/'backups', root/'genesis']
    # Any model explicitly named in a live process stays protected, even between opens.
    for pid in Path('/proc').iterdir():
        if not pid.name.isdigit():
            continue
        try:
            args = (pid/'cmdline').read_bytes().split(b'\0')
            for arg in args:
                text = arg.decode(errors='replace')
                for candidate in (text, text.split('=', 1)[-1]):
                    if candidate.startswith(str(root) + '/'):
                        values.append(Path(candidate))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            fail('PROCESS_SCAN_PERMISSION_REQUIRED')
    return sorted({str(p.resolve()) for p in values})


def evict_candidate(root, path, protected):
    rel = path.relative_to(root)
    if len(rel.parts) < 2 or rel.parts[0] not in {'models', 'judge'} or path.suffix.lower() != '.gguf':
        return False
    if path.is_symlink() or path.stat().st_nlink != 1:
        return False
    return not any(path.resolve() == Path(p) or Path(p) in path.resolve().parents for p in protected)


def validate_manifest(manifest, root, session):
    if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1 or
            manifest.get('instance_id') != 60509551 or manifest.get('session') != session or
            manifest.get('root') != str(root)):
        fail('MANIFEST_IDENTITY_MISMATCH')
    rows = manifest.get('files')
    if not isinstance(rows, list) or not rows:
        fail('MANIFEST_FILE_SCHEMA')
    seen, total = set(), 0
    for row in rows:
        if not isinstance(row, dict):
            fail('MANIFEST_FILE_SCHEMA')
        source = safe_relative(row.get('source_rel'))
        restore = safe_relative(row.get('restore_rel'))
        if source.casefold() in seen:
            fail('MANIFEST_DUPLICATE_SOURCE')
        seen.add(source.casefold())
        if (type(row.get('bytes')) is not int or row['bytes'] < 0 or
                not isinstance(row.get('sha256'), str) or not SHA.fullmatch(row['sha256']) or
                type(row.get('evict_candidate')) is not bool):
            fail('MANIFEST_FILE_SCHEMA')
        if row.get('kind') == 'file':
            if source != restore:
                fail('MANIFEST_SOURCE_MAPPING')
        elif row.get('kind') in {'file_snapshot', 'sqlite_snapshot'}:
            if source != 'state/pc_exports/' + session + '/snapshots/' + restore or row['evict_candidate']:
                fail('MANIFEST_SOURCE_MAPPING')
        else:
            fail('MANIFEST_FILE_SCHEMA')
        ident = row.get('identity')
        if not isinstance(ident, list) or len(ident) != 5 or any(type(v) is not int or v < 0 for v in ident):
            fail('MANIFEST_FILE_IDENTITY')
        if ident[2] != row['bytes']:
            fail('MANIFEST_FILE_IDENTITY')
        total += row['bytes']
    if type(manifest.get('total_bytes')) is not int or manifest['total_bytes'] != total:
        fail('MANIFEST_TOTAL_MISMATCH')
    return manifest


def write_selection(stage, manifest):
    # Regenerate deterministically on a resumed plan, including after a crash
    # between manifest publication and creation of selected.txt.
    destination = stage/'selected.txt'
    if destination.is_symlink():
        fail('SYMLINK_SELECTION_FILE')
    fd, temporary = tempfile.mkstemp(prefix='.selection-', dir=stage)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write(''.join(row['source_rel']+'\n' for row in manifest['files']))
            out.flush(); os.fsync(out.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_plan(root, session):
    stage = stage_dir(root, session)
    manifest_path = stage/'manifest.json'
    if manifest_path.exists():
        if manifest_path.is_symlink():
            fail('SYMLINK_MANIFEST')
        obj = validate_manifest(json.loads(manifest_path.read_text()), root, session)
        write_selection(stage, obj)
        return obj
    protected = active_paths(root)
    files, omitted, aliases, seen_windows = [], [], [], set()
    for folder, dirs, names in os.walk(root, followlinks=False):
        folder = Path(folder)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not SECRET_NAMES.search(d) and not (folder/d).is_symlink())
        for name in sorted(names):
            source = folder/name
            rel = source.relative_to(root).as_posix()
            try:
                safe_relative(rel)
            except RuntimeError as e:
                omitted.append({'path': rel, 'reason': str(e)}); continue
            lower = rel.casefold()
            if lower in seen_windows:
                fail('WINDOWS_CASE_COLLISION')
            seen_windows.add(lower)
            if source.is_symlink():
                target = source.resolve()
                if target.is_relative_to(root):
                    aliases.append({'path':rel, 'target':target.relative_to(root).as_posix()})
                continue
            s = source.stat()
            if not stat.S_ISREG(s.st_mode):
                continue
            if name.endswith(('-wal', '-shm', '-journal')):
                omitted.append({'path':rel, 'reason':'SQLITE_SIDECAR_USE_DATABASE_SNAPSHOT'}); continue
            if looks_secret(source):
                omitted.append({'path':rel, 'reason':'CREDENTIAL_OR_SECRET_CONTENT'}); continue
            if not archive_safe(source):
                omitted.append({'path':rel, 'reason':'ARCHIVE_CREDENTIAL_OR_UNINSPECTED_FORMAT'}); continue
            is_sqlite = sqlite_file(source) if s.st_size >= 16 else False
            snapshot = is_sqlite or (source.suffix.lower() not in BINARY_SUFFIX and s.st_size <= 64*1024*1024)
            physical, kind = source, 'file'
            if snapshot:
                if shutil.disk_usage(stage).free < s.st_size + 6*GIB:
                    fail('SNAPSHOT_DISK_RESERVE_6GIB_REQUIRED')
                physical = stage/'snapshots'/rel
                if is_sqlite:
                    snapshot_sqlite(source, physical); kind = 'sqlite_snapshot'
                else:
                    copy_snapshot(source, physical); kind = 'file_snapshot'
            before = identity(physical)
            digest = sha256(physical)
            if identity(physical) != before:
                fail('SOURCE_CHANGED_RETRY_NEW_SESSION')
            physical_rel = physical.relative_to(root).as_posix()
            files.append({'source_rel':physical_rel, 'restore_rel':rel, 'bytes':before[2],
                          'sha256':digest, 'identity':before, 'kind':kind,
                          'evict_candidate':not snapshot and evict_candidate(root, source, protected)})
    if not files:
        fail('NO_BACKUP_FILES_FOUND')
    obj = {'schema_version':1, 'instance_id':60509551, 'session':session,
           'created_at':time.time(), 'root':str(root), 'files':files,
           'total_bytes':sum(row['bytes'] for row in files),
           'sqlite_databases':sum(row['kind']=='sqlite_snapshot' for row in files),
           'aliases':aliases, 'omitted':omitted,
           'note':'Live SQLite is transaction-consistent per database; this is not a simultaneous checkpoint of all running processes.'}
    validate_manifest(obj, root, session)
    atomic_json(manifest_path, obj)
    write_selection(stage, obj)
    return obj


def validate_receipt(manifest, receipt, manifest_sha):
    if receipt.get('schema_version') != 1 or receipt.get('session') != manifest['session']:
        fail('RECEIPT_SCHEMA_MISMATCH')
    if receipt.get('manifest_sha256') != manifest_sha or receipt.get('all_verified') is not True:
        fail('RECEIPT_NOT_FULLY_VERIFIED')
    rows = receipt.get('files')
    if not isinstance(rows, list) or len(rows) != len(manifest['files']):
        fail('RECEIPT_INCOMPLETE')
    by_path = {r.get('source_rel'):r for r in rows}
    if len(by_path) != len(rows):
        fail('RECEIPT_DUPLICATE')
    for source in manifest['files']:
        row = by_path.get(source['source_rel'], {})
        if row.get('bytes') != source['bytes'] or row.get('local_sha256') != source['sha256'] or row.get('drive_sha256') != source['sha256']:
            fail('RECEIPT_SHA_MISMATCH')
    remote = receipt.get('drive_remote', '')
    if not re.fullmatch(r'nox_drive:[A-Za-z0-9_-]+', remote) or remote != 'nox_drive:'+manifest['session']:
        fail('RECEIPT_REMOTE_MISMATCH')
    return remote


def validate_pc_receipt(manifest, receipt, manifest_sha):
    """PC-only evidence cannot satisfy the separate PC+Drive deletion gate."""
    if (receipt.get('schema') != 'NOX_PC_OVERFLOW_V1' or receipt.get('session') != manifest['session']
            or receipt.get('manifest_sha256') != manifest_sha
            or receipt.get('pc_verified') is not True or receipt.get('drive_verified') is not False
            or receipt.get('server_sources_retained') is not True):
        fail('PC_OVERFLOW_RECEIPT_SCHEMA')
    target = receipt.get('pc_backup_root')
    if not isinstance(target, str) or any(ord(c) < 32 for c in target):
        fail('PC_OVERFLOW_BACKUP_ROOT')
    windows = PureWindowsPath(target)
    if (not windows.is_absolute() or not re.fullmatch('[A-Za-z]:', windows.drive)
            or '..' in windows.parts or any(c in target for c in '?*<>|"')):
        fail('PC_OVERFLOW_BACKUP_ROOT')
    relative = 'BACKUPS/'+manifest['session']+'/data'
    if receipt.get('pc_session_rel') != relative:
        fail('PC_OVERFLOW_SESSION_SCOPE')
    rows = receipt.get('files')
    if not isinstance(rows, list) or len(rows) != len(manifest['files']) or any(not isinstance(row, dict) for row in rows):
        fail('PC_OVERFLOW_RECEIPT_INCOMPLETE')
    by_path = {row.get('source_rel'):row for row in rows}
    if len(by_path) != len(rows):
        fail('PC_OVERFLOW_RECEIPT_DUPLICATE')
    for original in manifest['files']:
        row = by_path.get(original['source_rel'], {})
        if row.get('bytes') != original['bytes'] or row.get('local_sha256') != original['sha256']:
            fail('PC_OVERFLOW_LOCAL_SHA_MISMATCH')
        if row.get('drive_sha256') not in (None, ''):
            fail('PC_OVERFLOW_MUST_NOT_CLAIM_DRIVE_COPY')
    return windows, relative


def backup_role(relative):
    """Keep canonical weights, optimizer checkpoints and caches distinguishable."""
    path = PurePosixPath(relative)
    if 'merged_hf' in path.parts and path.parts[0] == 'progress_pull_t784u':
        return 'canonical_trainable_base'
    if any(re.fullmatch(r'checkpoint-\d+', part) for part in path.parts):
        return 'optimizer_checkpoint_component'
    if path.parts[0] == 'lora':
        return 'adapter_or_training_lineage'
    if path.suffix.lower() == '.gguf':
        return 'inference_model'
    if path.suffix.lower() == '.safetensors':
        return 'model_weight_component'
    return 'project_backup'


def _register_pc_locked(root, session):
    """Persist local full-readback evidence even when Drive is unavailable.

    This is an authenticated owner-PC receipt, not a claim that the server has
    already read the PC through the permanent reverse tunnel. It provides no
    eviction path, and retains all canonical/training source files.
    """
    stage = stage_dir(root, session)
    manifest_file = plain_source(root, 'state/pc_exports/'+session+'/manifest.json')
    manifest = validate_manifest(json.loads(manifest_file.read_text()), root, session)
    receipt_path = plain_source(root, 'state/pc_exports/'+session+'/pc_verified.json')
    receipt = json.loads(receipt_path.read_text())
    windows, relative = validate_pc_receipt(manifest, receipt, sha256(manifest_file))
    catalog_path = plain_source(root, 'state/pc_overflow_catalog.json')
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
        if catalog.get('schema') != 'NOX_PC_OVERFLOW_CATALOG_V1' or not isinstance(catalog.get('sessions'), dict):
            fail('PC_OVERFLOW_CATALOG_SCHEMA')
    else:
        catalog = {'schema':'NOX_PC_OVERFLOW_CATALOG_V1', 'sessions':{}}
    item = {'session':session, 'manifest_sha256':sha256(manifest_file),
            'pc_receipt_sha256':sha256(receipt_path), 'pc_backup_root':str(windows),
            'pc_session_rel':relative, 'verified_at':time.time(), 'pc_verified':True,
            'server_readback_verified':False, 'drive_verified':False,
            'eviction_allowed':False, 'server_sources_retained':True,
            'total_bytes':manifest['total_bytes'], 'models':[]}
    for row in manifest['files']:
        role = backup_role(row['restore_rel'])
        if role != 'project_backup':
            item['models'].append({'restore_rel':row['restore_rel'], 'pc_relative_path':relative+'/'+row['source_rel'],
                                   'bytes':row['bytes'], 'sha256':row['sha256'], 'role':role,
                                   'resume_or_promotion_verified':False})
    old = catalog['sessions'].get(session)
    if old and (old.get('manifest_sha256') != item['manifest_sha256']
                or old.get('pc_backup_root') != item['pc_backup_root']):
        fail('PC_OVERFLOW_SESSION_IDENTITY_CHANGED')
    catalog['sessions'][session] = item
    atomic_json(catalog_path, catalog)
    result = {'schema':'NOX_PC_OVERFLOW_RESULT_V1', 'session':session,
              'pc_verified':True, 'drive_verified':False, 'server_readback_verified':False,
              'eviction_allowed':False, 'evicted':[], 'server_sources_retained':True,
              'catalog':str(catalog_path), 'total_bytes':manifest['total_bytes'],
              'note':'Drive remains pending; PC receipt alone never authorizes source deletion.'}
    atomic_json(stage/'pc_result.json', result)
    return result


def register_pc(root, session):
    import nox_cold_drive as cold
    with cold.maintenance_lock(root/'state/cold_drive_receipts'):
        return _register_pc_locked(root, session)


def finalize(root, session, evict=False):
    stage = stage_dir(root, session)
    manifest_file = plain_source(root, 'state/pc_exports/'+session+'/manifest.json')
    manifest = validate_manifest(json.loads(manifest_file.read_text()), root, session)
    receipt_file = plain_source(root, 'state/pc_exports/'+session+'/verified.json')
    receipt = json.loads(receipt_file.read_text())
    remote = validate_receipt(manifest, receipt, sha256(manifest_file))
    config = plain_source(root, 'state/cold_drive.conf')
    if not config.is_file() or stat.S_IMODE(config.stat().st_mode) != 0o600:
        fail('PRIVATE_DRIVE_CONFIG_0600_REQUIRED')
    os.environ['RCLONE_CONFIG'] = str(config)
    import nox_cold_drive as cold
    catalog = {'schema_version':1, 'session':session, 'verified_at':time.time(),
               'rclone_config':str(config), 'models':[]}
    removed, held = [], []
    with cold.maintenance_lock(root/'state/cold_drive_receipts'):
        for row in manifest['files']:
            if Path(row['restore_rel']).suffix.lower() in {'.gguf','.safetensors'}:
                catalog['models'].append({'restore_rel':row['restore_rel'], 'remote':remote+'/'+row['source_rel'],
                                          'bytes':row['bytes'], 'sha256':row['sha256']})
            if not evict or row.get('evict_candidate') is not True:
                continue
            src = plain_source(root, row['restore_rel'])
            try:
                protected = active_paths(root)
                if not evict_candidate(root, src, protected):
                    fail('NOW_ACTIVE_OR_PROTECTED')
                if identity(src) != row['identity'] or sha256(src) != row['sha256']:
                    fail('SOURCE_CHANGED')
                destination = remote+'/'+row['source_rel']
                # Server independently checks the actual remote bytes before unlink.
                if cold.stream_sha256(destination, row['bytes'], 24*3600) != row['sha256']:
                    fail('REMOTE_SHA_MISMATCH')
                active_file = stage/'evict_active.json'
                atomic_json(active_file, {'generated_at':time.time(), 'active_paths':active_paths(root),
                                          'protected_paths':[], 'evict_paths':[str(src)]})
                record = {'source':str(src), 'destination':destination, 'identity':row['identity'],
                          'size':row['bytes'], 'sha256':row['sha256'], 'readback_verified':True,
                          'verified_at':time.time(), 'source_deleted':False,
                          'receipt':str(root/'state/cold_drive_receipts'/(row['sha256']+'.json'))}
                removed.append(cold.evict_verified(record, active_file))
            except (RuntimeError, ValueError, FileNotFoundError) as e:
                held.append({'path':row['restore_rel'], 'reason':str(e)})
    atomic_json(root/'state/cold_drive_catalog.json', catalog)
    with cold.maintenance_lock(root/'state/cold_drive_receipts'):
        pc_catalog_path = plain_source(root, 'state/pc_overflow_catalog.json')
        if pc_catalog_path.is_file():
            pc_catalog = json.loads(pc_catalog_path.read_text())
            entry = (pc_catalog.get('sessions') or {}).get(session)
            if (pc_catalog.get('schema') != 'NOX_PC_OVERFLOW_CATALOG_V1'
                    or (entry and entry.get('manifest_sha256') != sha256(manifest_file))):
                fail('PC_OVERFLOW_CATALOG_IDENTITY_CHANGED')
            if entry:
                entry.update(drive_verified=True, drive_remote=remote,
                             drive_finalize_at=time.time(), server_sources_retained=not bool(removed),
                             eviction_requested=bool(evict), evicted_count=len(removed))
                atomic_json(pc_catalog_path, pc_catalog)
    result = {'schema_version':1, 'session':session, 'copies_verified':True,
              'evicted':removed, 'held':held, 'catalog':str(root/'state/cold_drive_catalog.json'),
              'disk_free_bytes':shutil.disk_usage(root).free}
    atomic_json(stage/'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for cmd in ('plan','register-pc','finalize'):
        p = sub.add_parser(cmd); p.add_argument('--session', required=True)
        if cmd == 'finalize':
            p.add_argument('--evict-inactive-gguf', action='store_true')
    a = parser.parse_args()
    if a.command == 'plan':
        obj = build_plan(ROOT, a.session)
        print(json.dumps({'session':a.session, 'files':len(obj['files']),
                          'bytes':obj['total_bytes'], 'sqlite_databases':obj['sqlite_databases'],
                          'omitted':len(obj['omitted'])}))
    elif a.command == 'register-pc':
        print(json.dumps(register_pc(ROOT, a.session)))
    else:
        print(json.dumps(finalize(ROOT, a.session, a.evict_inactive_gguf)))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No provider stderr or source contents are emitted.
        print(json.dumps({'ok':False, 'error':type(exc).__name__, 'code':str(exc)[:160]}), file=sys.stderr)
        sys.exit(1)
