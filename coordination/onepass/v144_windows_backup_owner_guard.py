"""NOX V144: fail closed original Windows backup UI callsites in the full V140 WEB.

No backend, URL rewrite, silent cloud fallback, or live native action is introduced.
The original V140 ZIP stays immutable; three exact JS entries are updated, their
original bytes are retained in the candidate ZIP's rollback/ directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import zipfile
from pathlib import Path

INPUT_SHA256 = '3bb79b1edfa9715438dd81010d1e945fe11c678e0a1dddeefd19ae2896917c6f'
INPUT_MEMBERS = 1132
TARGETS = ('site/workspace-pages.js', 'site/pc/workspace-pages.js', 'site/pc/v23/nox-v23.js')
ROLLBACK = 'rollback/v144/'
MANIFEST = 'NOX_V144_WINDOWS_BACKUP_OWNER_SOURCE_MANIFEST.json'
ANCHOR = 'const page=document.body.dataset.page,native=workspace.native===true;'
OLD_ACTION = "await api('/api/install/backup',{})"
FALLBACK_OLD = "await call('/api/install/backup', {confirm: true})"
GUARD = r'''
/* V144 source gate, not a substitute for Windows server-side owner cookie/ACL. */
const windowsOwnerBackup = async () => {
  const pc = location.protocol === 'http:' &&
    ['127.0.0.1','localhost','[::1]'].includes(location.hostname) &&
    location.port === '8766';
  if (!pc || native !== true || window.NOX_NATIVE_OWNER !== true)
    throw Error('HOLD_WINDOWS_BACKUP_WRONG_HOST_OR_ANONYMOUS');
  const identity = await api('/api/nox/status');
  // The 92-route baseline locates /api/nox/status on OneHost, NOT the
  // Windows PC. OneHost's own READY+owner response cannot authorize a
  // Windows-only backup even if a separate capability fixture says yes.
  // A real Windows status handler must independently identify its PC role.
  // Until its native schema/owner cookie is proven, this fails closed.
  if (identity?.status !== 'READY' || identity?.host !== 'NOX_CHAT_V24.1' ||
      identity?.owner_authenticated !== true || identity?.windows_owner_pc !== true)
    throw Error('HOLD_WINDOWS_BACKUP_OWNER_IDENTITY_UNVERIFIED');
  const ability = await api('/api/install/capabilities');
  if (ability?.status !== 'READY' || ability?.windows_owner_pc !== true ||
      ability?.owner_authenticated !== true || ability?.backup_supported !== true)
    throw Error('HOLD_WINDOWS_BACKUP_OWNER_CAPABILITY_UNVERIFIED');
  const result = await api('/api/install/backup', {confirm:true});
  if (result?.status !== 'READY' || result?.sha256_verified !== true ||
      typeof result?.backup_sha256 !== 'string' ||
      !/^[a-f0-9]{64}$/i.test(result.backup_sha256))
    throw Error('HOLD_WINDOWS_BACKUP_NATIVE_SHA_RECEIPT_UNVERIFIED');
  return result;
};
window.NOX_WINDOWS_BACKUP_V144 = Object.freeze({backup:windowsOwnerBackup});
'''.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1 << 20), b''):
            h.update(part)
    return h.hexdigest()


def patched(name: str, source: bytes) -> bytes:
    body = source.decode('utf8')
    if name in TARGETS[:2]:
        if body.count(ANCHOR) != 1 or body.count(OLD_ACTION) != 1 or 'NOX_WINDOWS_BACKUP_V144' in body:
            raise ValueError('HOLD_ORIGINAL_WINDOWS_BACKUP_ANCHOR_' + name)
        body = body.replace(ANCHOR, ANCHOR + '\n' + GUARD, 1)
        body = body.replace(OLD_ACTION, 'await window.NOX_WINDOWS_BACKUP_V144.backup()', 1)
    elif name == TARGETS[2]:
        if body.count(FALLBACK_OLD) != 1 or 'NOX_WINDOWS_BACKUP_V144' in body:
            raise ValueError('HOLD_V23_BACKUP_ANCHOR')
        body = body.replace(FALLBACK_OLD,
                            "await (window.NOX_WINDOWS_BACKUP_V144?.backup?.() ?? "
                            "Promise.reject(Error('HOLD_WINDOWS_BACKUP_GUARD_NOT_BOUND')))", 1)
    else:
        raise ValueError('HOLD_NONCANONICAL_TARGET')
    return body.encode('utf8')


def zip_add(z: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2026, 11, 15, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    z.writestr(info, data)


def verify(source: Path, candidate: Path) -> dict:
    if file_sha(source) != INPUT_SHA256:
        raise ValueError('HOLD_V140_INPUT_SHA_DRIFT')
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(candidate) as out:
        names = original.namelist()
        after = out.namelist()
        if len(names) != INPUT_MEMBERS or len(set(names)) != INPUT_MEMBERS:
            raise ValueError('HOLD_V140_MEMBER_COUNT_OR_DUPLICATES')
        if original.testzip() is not None or out.testzip() is not None:
            raise ValueError('HOLD_ZIP_CRC')
        if len(after) != INPUT_MEMBERS + len(TARGETS) + 1 or len(set(after)) != len(after):
            raise ValueError('HOLD_V144_MEMBER_COUNT_OR_DUPLICATES')
        if set(after) != set(names) | {ROLLBACK + p for p in TARGETS} | {MANIFEST}:
            raise ValueError('HOLD_V144_UNEXPECTED_PATHS')
        m = json.loads(out.read(MANIFEST))
        if m.get('source_sha256') != INPUT_SHA256 or m.get('production_deployed') is not False:
            raise ValueError('HOLD_V144_MANIFEST_SOURCE_SCOPE')
        if set(m.get('patches', {})) != set(TARGETS):
            raise ValueError('HOLD_V144_MANIFEST_PATCH_SET')
        for name in names:
            before = original.read(name)
            result = out.read(name)
            if name in TARGETS:
                if (out.read(ROLLBACK + name) != before or result != patched(name, before) or
                        m['patches'][name] != {'before_sha256': sha(before), 'after_sha256': sha(result)}):
                    raise ValueError('HOLD_V144_ROLLBACK_OR_PATCH_' + name)
            elif result != before:
                raise ValueError('HOLD_V144_UNEXPECTED_ORIGINAL_MODIFICATION_' + name)
    return {'status':'SOURCE_ONLY_VERIFIED', 'input_members':INPUT_MEMBERS,
            'output_members':INPUT_MEMBERS+len(TARGETS)+1,
            'untouched_original_members':INPUT_MEMBERS-len(TARGETS),
            'patched_original_members':len(TARGETS),'rollback_verified':True,
            'native_owner_cookie_verified':False,'windows_E2E_verified':False}


def build(source: Path, output: Path) -> dict:
    source, output = Path(source), Path(output)
    if file_sha(source) != INPUT_SHA256:
        raise ValueError('HOLD_V140_INPUT_SHA_DRIFT')
    if output.exists() or output.is_symlink() or output.resolve() == source.resolve():
        raise ValueError('HOLD_OUTPUT_ALREADY_EXISTS')
    temp = output.with_name(output.name + '.v144-pending')
    if temp.exists() or temp.is_symlink():
        raise ValueError('HOLD_PENDING_EXISTS')
    patches = {}
    try:
        with zipfile.ZipFile(source) as original:
            names = original.namelist()
            if len(names) != INPUT_MEMBERS or len(set(names)) != INPUT_MEMBERS or original.testzip() is not None:
                raise ValueError('HOLD_V140_ORIGINAL_INTEGRITY')
            if not set(TARGETS).issubset(names) or MANIFEST in names or any(ROLLBACK + t in names for t in TARGETS):
                raise ValueError('HOLD_V140_TARGETS_MISSING_OR_ALREADY_PATCHED')
            with zipfile.ZipFile(temp, 'x', allowZip64=True) as out:
                for info in original.infolist():
                    before = original.read(info)
                    if info.filename in TARGETS:
                        result = patched(info.filename, before)
                        patches[info.filename] = {'before_sha256':sha(before), 'after_sha256':sha(result)}
                        zip_add(out, ROLLBACK + info.filename, before)
                        out.writestr(copy.copy(info), result)
                    else:
                        out.writestr(copy.copy(info), before)
                zip_add(out, MANIFEST, (json.dumps({
                    'schema':'NOX_V144_WINDOWS_BACKUP_OWNER_SOURCE_ONLY_V1',
                    'instructions_version':'0.0.6',
                    'source_sha256':INPUT_SHA256, 'source_entries':INPUT_MEMBERS,
                    'patches':patches,'production_deployed':False,
                    'native_owner_cookie_verified':False,
                    'windows_owner_backup_handler_verified':False,
                    'original_s03_weights_checkpoints_unchanged':True,
                    'existing_windows_backend_only':True,
                },indent=2,sort_keys=True)+'\n').encode('utf8'))
        proof = verify(source, temp)
        os.link(temp, output)  # atomic no-replace; source remains untouched
        temp.unlink()
        return {'candidate_sha256':file_sha(output),**proof}
    finally:
        temp.unlink(missing_ok=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--v140-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    opts = p.parse_args()
    print(json.dumps(build(opts.v140_source,opts.output),sort_keys=True))
