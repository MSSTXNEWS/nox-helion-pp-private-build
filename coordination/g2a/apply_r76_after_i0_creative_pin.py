"""NOX HELION R76 · exact GitLab donor → existing owner1 OneHost source.

This modifies only the owner's disposable checkout and NEVER builds, publishes,
merges, or installs. It refuses an unknown owner script, unknown donor version,
changed asset, symlink/junction, missing WOW pair, or partial previous patch.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import subprocess
from pathlib import Path

OWNER_SHA1 = '19e6f9ce69bc3bb45c0e6676082a8a04487929e6'
GITLAB_SHA = 'b0b9c34c89dc5b3799d7c5bb19b32a74a3f10205'

# Actual GitLab R76 tree at GITLAB_SHA. These are TRANSPORT file SHA-1 Git
# blobs; the staging code separately proves decoded original PNG SHA-256.
DONOR_BLOBS = {
    'stage_original_r11.py': 'a0e7e24bea8817c55e033f3cf58955ef77c278fe',
    'publish_onehost_payload.py': '07202590952d81c5e4d63a0c356059356e9e1eeb',
    'manifest.json': '2b98f4c4182750eedcec879f5e2e696167aaf4e9',
    'mega814.mjs': 'c3c91bae4f22214c0e39d0e1b95e1ccef1205bd4',
    'mega814.css': '24e5eecf7d55994f6b2e1f32c296305503a63d5a',
    'menu-v2-193.json': 'a57ced96e6edb5d77d99a83f945c47dbe97bbaf8',
    'menu-v2-adapter.mjs': '7cbbea82529259403320bdb7b06b05fd2dc34c8e',
    'native-readonly.mjs': 'e698d3605646df0e2d39c7f2943c55d2364778c0',
    'owner-dispatch.mjs': 'f4eb000843bc78af116e4015ed06528b032ee991',
    'owner-e05.mjs': '1dcf0df656cdce6f4231f5f411db9150d0768ead',
    'approved_menu10.png': '0b2bade416d93ff6cd9b4f6ece9e66370d96b526',
    'approved_persona/ADRIAN_OWNER_APPROVED_IDENTITY_MASTER_20261020.png': '9dd85d1400e36e2ccdc6744cb6332a1775e2e381',
    'approved_persona/LE-M24-01.png': '2fea70a2e14e3a80faf10c18a998a882bceba057',
    'approved_persona/NOX_HELION_HOME_OWNER_APPROVED_20261019.png': '1611fd32ef361757b6d48836d62545f44c771532',
    'approved_persona/NOX_KW_KASSIEN_OWNER_APPROVED_PASSPORT_20261020.png': '6bc2d2374e4e13df5e1bfe51c942a0ef61f3a43c',
    'reference/NOX_HELION_MENU_LAVA_WORLD_CURRENT_20261022.png': 'abe651578bc551b900b443040191842aae3056e5',
}


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def ordinary_file(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or (hasattr(candidate, 'is_junction') and candidate.is_junction()):
            return False
    return True


def verify_donor(donor: Path) -> dict[str, str]:
    """Ensure all sixteen source/asset files match exact GitLab R76 bytes.

    Read-only. SHA1 here is solely Git transport identity; all approved PNG
    pixels still require their independent SHA256 in stage_original_r11.py.
    """
    if not donor.is_dir() or donor.is_symlink():
        raise RuntimeError('MEGAB_DONOR_DIRECTORY_MISSING')
    if donor.name != 'mega814' or donor.parent.name != 'coordination':
        raise RuntimeError('MEGAB_DONOR_REPO_LAYOUT_HOLD')
    gitroot = donor.parent.parent
    result_head = subprocess.run(
        ['git', '-C', str(gitroot), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=False,
    )
    if result_head.returncode != 0 or result_head.stdout.strip().lower() != GITLAB_SHA:
        raise RuntimeError('MEGAB_DONOR_GIT_HEAD_MISMATCH')
    result = {}
    for name, expected in DONOR_BLOBS.items():
        target = donor.joinpath(*name.split('/'))
        if not ordinary_file(target):
            raise RuntimeError('MEGAB_DONOR_FILE_NOT_REGULAR:' + name)
        actual = git_blob(target.read_bytes())
        if actual != expected:
            raise RuntimeError('MEGAB_DONOR_SHA_MISMATCH:' + name)
        result[name] = actual
    return result


PS_PARAM = " [string]$PersonaBundlePath=''\n)"
PS_PARAM_NEW = " [string]$PersonaBundlePath='',\n [string]$MegaBSourceRoot=''\n)"
PS_STAGE_ANCHOR = "if (Test-Path -LiteralPath $OutputRoot) { throw 'OUTPUT_ALREADY_EXISTS_NO_OVERWRITE' }"
PS_PAYLOAD_ANCHOR = "$backend=Join-Path $payload 'Backend'"


def ps_donor_pins() -> str:
    rows = '\n'.join(
        "    '" + key + "'='" + val + "'"
        for key, val in DONOR_BLOBS.items()
    )
    return '@{\n' + rows + '\n  }'


STAGE_FRAGMENT = """# R76 optional owner-2 MENU10 graft; strict original D02/WOW200 only.
$wantsMegaB= -not [string]::IsNullOrWhiteSpace($MegaBSourceRoot)
if ($wantsMegaB) {
  if (!$wantsCreative -or !$wantsWow) { throw 'MEGAB_REQUIRES_APPROVED_D02_WOW200' }
  Assert-E06PlainPathAncestors -Candidate $MegaBSourceRoot -Scope 'MEGAB'
  $megaB=(Resolve-Path -LiteralPath $MegaBSourceRoot -ErrorAction Stop).Path
  # The donor source is checked out at /coordination/mega814 of ONE GitLab repo.
  if ((Split-Path -Leaf $megaB) -cne 'mega814' -or
      (Split-Path -Leaf (Split-Path -Parent $megaB)) -cne 'coordination') {
    throw 'MEGAB_DONOR_REPO_LAYOUT_HOLD'
  }
  $megaRepo=Split-Path -Parent (Split-Path -Parent $megaB)
  $repoHeadOutput=@(& $git.Source -C $megaRepo rev-parse HEAD)
  if ($LASTEXITCODE -ne 0 -or $repoHeadOutput.Count -ne 1) { throw 'MEGAB_R76_DONOR_HEAD_HOLD' }
  $repoCommit=([string]$repoHeadOutput[0]).Trim().ToLowerInvariant()
  if ($repoCommit -cne '@@COMMIT@@') {
    throw 'MEGAB_R76_DONOR_HEAD_HOLD'
  }
  $pinned=@@PINS@@
  foreach ($name in $pinned.Keys) {
    $target=Join-Path $megaB $name
    Assert-E06PlainPathAncestors -Candidate $target -Scope 'MEGAB_ASSET'
    if (!(Test-Path -LiteralPath $target -PathType Leaf)) { throw 'MEGAB_DONOR_ASSET_MISSING' }
    $info=Get-Item -LiteralPath $target -Force
    if (($info.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw 'MEGAB_DONOR_ASSET_REPARSE_HOLD'
    }
    $actual=(& $git.Source hash-object -- $target).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $actual -cne $pinned[$name]) {
      throw 'MEGAB_R76_DONOR_BLOB_MISMATCH:'+$name
    }
  }
  & $py.Source (Join-Path $megaB 'stage_original_r11.py') --r11 $source
  if ($LASTEXITCODE -ne 0) { throw 'MEGAB_OWNER_D02_STAGE_HOLD' }
}
""".replace('@@COMMIT@@', GITLAB_SHA).replace('@@PINS@@', ps_donor_pins())

PUBLISH_FRAGMENT = """# R76: approve exactly 14 SHA-pinned original MENU10 files before NSIS manifest.
if ($wantsMegaB) {
  & $py.Source (Join-Path $megaB 'publish_onehost_payload.py') --r11 $source --payload $payload
  if ($LASTEXITCODE -ne 0) { throw 'MEGAB_OWNER_PAYLOAD_SHA_HOLD' }
}
"""


def patched(original: bytes) -> bytes:
    if git_blob(original) != OWNER_SHA1:
        raise RuntimeError('OWNER_ONEHOST_BUILDER_EXACT_GIT_BLOB_MISMATCH')
    if b'\r\n' in original:
        raise RuntimeError('OWNER_ONEHOST_CRLF_MODE_REQUIRES_REVIEW')
    txt = original.decode('utf-8')
    changes = (
        (PS_PARAM, PS_PARAM_NEW),
        (PS_STAGE_ANCHOR, STAGE_FRAGMENT + PS_STAGE_ANCHOR),
        (PS_PAYLOAD_ANCHOR, PUBLISH_FRAGMENT + PS_PAYLOAD_ANCHOR),
    )
    for old, new in changes:
        if txt.count(old) != 1:
            raise RuntimeError('OWNER_ONEHOST_ANCHOR_NOT_UNIQUE:' + old[:72])
        txt = txt.replace(old, new, 1)
    if txt.count('MEGAB_R76_DONOR_BLOB_MISMATCH') != 1 or txt.count('MEGAB_OWNER_PAYLOAD_SHA_HOLD') != 1:
        raise RuntimeError('OWNER_ONEHOST_PATCH_CONTENT_HOLD')
    return txt.encode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--builder', required=True, type=Path)
    parser.add_argument('--donor', type=Path, help='Exact GitLab R76 coordination/mega814 directory')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    target = args.builder
    if not ordinary_file(target):
        raise RuntimeError('OWNER_ONEHOST_BUILDER_PATH_OR_REPARSE_HOLD')
    original = target.read_bytes()
    new = patched(original)
    if args.donor:
        donor = args.donor
        pins = verify_donor(donor)
        print('DONOR_16_OF_16_GIT_BLOB_PASS', len(pins))
    elif args.apply:
        raise RuntimeError('MEGAB_DONOR_REQUIRED_FOR_WRITE')
    print('OWNER_SOURCE_SHA_PASS', OWNER_SHA1,
          'PATCH_SHA256', hashlib.sha256(new).hexdigest())
    if not args.apply:
        return 0
    # Exclusive create is portable on Windows; never open a directory with os.open.
    temp = target.with_name(target.name + '.megab-temp')
    backup = target.with_name(target.name + '.megab-r76-preimage')
    if temp.exists() or temp.is_symlink() or backup.exists() or backup.is_symlink():
        raise RuntimeError('MEGAB_OWNER_STAGE_OR_BACKUP_COLLISION')
    # Backup allows local rollback. Existing branch, CI, and release are untouched.
    backup_created = False
    try:
        with backup.open('xb') as handle:
            backup_created = True
            handle.write(original)
            handle.flush()
            os.fsync(handle.fileno())
        with temp.open('xb') as handle:
            handle.write(new)
            handle.flush()
            os.fsync(handle.fileno())
        if not ordinary_file(target) or target.read_bytes() != original:
            raise RuntimeError('MEGAB_OWNER_PREIMAGE_RACE_HOLD')
        os.replace(temp, target)
        if target.read_bytes() != new:
            raise RuntimeError('MEGAB_OWNER_WRITE_READBACK_HOLD')
    except BaseException:
        if temp.exists():
            temp.unlink()
        # Restore original only if we had replaced it and still own the new bytes.
        if target.is_file() and target.read_bytes() == new and backup.is_file():
            os.replace(backup, target)
        elif backup_created and backup.is_file():
            backup.unlink()
        raise
    print('OWNER_SOURCE_ONLY_PATCH_APPLIED / BACKUP=' + backup.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())