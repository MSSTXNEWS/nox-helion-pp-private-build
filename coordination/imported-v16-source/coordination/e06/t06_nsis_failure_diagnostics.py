"""Read-only postmortem for an already failed disposable Windows install.

Never re-runs Setup, launches the app, removes a stage, or grants acceptance.
Reuse the original candidate/receipt/path gates and reviewed payload verifier.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import re
import stat
from pathlib import Path
import subprocess
import sys


def verify_failed_setup_identity(owner, failure: dict, evidence: dict) -> None:
    """Fail closed on immutable Setup SHA, respecting actual bridge receipt schema.

    The original LOCAL_BRIDGE candidate_gate rehashes physical Setup and
    revalidates exact source/WPF/OneHost/manifest provenance, but never emits a
    BuildID. Do not silently invent a BuildID or skip SHA verification.
    Other owner paths still MUST carry the same explicit nonempty BuildID.
    Read-only diagnostic admission does not authorize install or E07.
    """
    left = failure.get('setup_sha256')
    right = evidence.get('setup_sha256')
    owner.require(type(left) is str and type(right) is str and
                  re.fullmatch(r'[0-9a-f]{64}', right) is not None and
                  left == right,
                  'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD')
    if getattr(owner, 'ON_LOCAL_BRIDGE', False) is True:
        owner.require('build_id' not in failure and
                      'build_id' not in evidence,
                      'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD')
    else:
        a = failure.get('build_id')
        b = evidence.get('build_id')
        owner.require(type(a) is str and len(a) > 0 and
                      type(b) is str and a == b,
                      'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD')


def readonly_rollback_backup_verifier(owner, backup: Path) -> dict:
    """CI-only independent read-only probe following a FAILED original rollback.

    Never runs Setup, restores, deletes, or accepts an independent E07 case.
    Identifies whether the exact staged PowerShell 5.1 backup verifier itself
    accepts the backup after native NSIS returned nonzero.
    """
    result = {'status': 'NOT_VERIFIED', 'release_accepted': False,
              'independent_e07': 'NOT_RUN', 'original_rollback_exit_unchanged': True}
    script = owner.ROOT / 'work/e06/staged/R11/Installer/Verify-Payload.ps1'
    manifest = backup / 'payload.sha256.json'
    if not (owner.regular(script) and owner.regular(manifest) and
            owner.plain_parents(script, owner.ROOT) and
            owner.plain_parents(manifest, Path(backup.anchor))):
        result['status'] = 'SOURCE_OR_BACKUP_UNAVAILABLE_HOLD'
        return result
    try:
        raw = script.read_bytes()
    except OSError:
        result['status'] = 'STAGED_VERIFIER_READ_HOLD'
        return result
    guards = (b'Get-P01VerifiedSha256', b'Assert-P01UniqueManifestMembers',
              b'Assert-NoReparseAncestors', b'AllowInstalledUserFiles',
              b'AllowInstalledMetadata', b'P01_PAYLOAD_VERIFY_FAILED')
    if not (2048 <= len(raw) <= 131072 and all(raw.count(g) >= 1 for g in guards)):
        result['status'] = 'STAGED_VERIFIER_CONTRACT_HOLD'
        return result
    result['staged_verifier_sha256'] = hashlib.sha256(raw).hexdigest()
    # Exact original CI-owned staging only. This verifier never writes a file.
    observed = owner.run([
        'powershell.exe', '-NoProfile', '-NonInteractive',
        '-ExecutionPolicy', 'Bypass', '-File', str(script),
        '-Root', str(backup), '-Manifest', str(manifest),
        '-AllowInstalledMetadata', '-AllowInstalledUserFiles'], 130)
    code = observed.get('code')
    result['verifier_exit_code'] = code if type(code) is int else None
    # Keep raw stderr/paths out of persistent receipts.
    tail = str(observed.get('stdout_tail', '')) + '\n' + str(observed.get('stderr_tail', ''))
    if code == 0 and 'P01_PAYLOAD_SHA256_PASS' in tail:
        result['status'] = 'READ_ONLY_BACKUP_VERIFIER_PASS_NOT_ROLLBACK'
    elif 'ParameterBinding' in tail or 'parameter cannot be found' in tail:
        result['status'] = 'BACKUP_VERIFIER_PARAMETER_BINDING_HOLD'
    elif 'P01_PAYLOAD_VERIFY_FAILED' in tail:
        result['status'] = 'BACKUP_VERIFIER_PAYLOAD_ADMISSION_HOLD'
    else:
        result['status'] = 'BACKUP_VERIFIER_EXECUTION_HOLD'
    return result


def collect(owner, *, platform_name=None, env=None):
    env = os.environ if env is None else env
    platform_name = sys.platform if platform_name is None else platform_name
    owner.require(platform_name == 'win32' and
                  env.get('GITHUB_ACTIONS') == 'true' and
                  env.get('RUNNER_OS') == 'Windows' and
                  env.get('NOX_E07_CI_WINDOWS_DISPOSABLE') == 'YES' and
                  str(env.get('GITHUB_RUN_ID', '')).isascii() and
                  str(env.get('GITHUB_RUN_ID', '')).isdecimal(),
                  'T06_NSIS_DIAGNOSTICS_DISPOSABLE_WINDOWS_ONLY')
    failure_path = owner.OUTPUT / 'T06_INSTALLED_SMOKE.json'
    failure = owner.strict_receipt(failure_path, 'T06_NSIS_DIAGNOSTIC_RECEIPT_HOLD')
    # This postmortem is also needed when the original NSIS update or its
    # fail-closed installed-backup verifier failed on a real Windows runner.
    # Admit only observed original installer first-fails, never unrelated failures.
    owner.require(failure.get('reason') in (
                  'T06_NSIS_SILENT_INSTALL_FAILED',
                  'T06_ORIGINAL_NSIS_UPDATE_BACKUP_HOLD',
                  'T06_UPDATE_BACKUP_MANIFEST_VERIFY_HOLD',
                  'T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD') and
                  failure.get('phase') == 'HOLD' and
                  failure.get('release_accepted') is False,
                  'T06_NSIS_DIAGNOSTICS_NO_MATCHING_FAILURE')
    evidence = owner.candidate_gate()
    verify_failed_setup_identity(owner, failure, evidence)
    local = Path(env.get('LOCALAPPDATA', ''))
    owner.require(local.is_absolute() and local.is_dir() and
                  owner.plain_parents(local, Path(local.anchor)),
                  'T06_NSIS_DIAGNOSTICS_LOCAL_ROOT_HOLD')
    install = local / 'Programs' / 'NOX HELION'
    report = {'schema': 'NOX-T06-NSIS-FAILURE-DIAGNOSTICS-v1',
              'phase': 'DIAGNOSTIC_ONLY', 'release_accepted': False,
              'original_failure': failure['reason'],
              'setup_sha256': evidence['setup_sha256'],
              'slots': {}, 'verifications': []}
    if 'build_id' in evidence:
        report['build_id'] = evidence['build_id']
    for label, slot in (('stage', Path(str(install) + '.__p01_stage')),
                        ('installed', install),
                        ('previous', Path(str(install) + '.__p01_previous')),
                        ('rollback_saved', Path(str(install) + '.__p01_rollback_saved'))):
        safe = owner.plain_parents(slot, Path(local.anchor))
        owner.require(safe and not slot.is_symlink() and
                      not getattr(slot, 'is_junction', lambda: False)(),
                      'T06_NSIS_DIAGNOSTICS_REPARSE_HOLD')
        report['slots'][label] = {'exists': slot.exists(), 'directory': slot.is_dir()}
        if slot.is_dir():
            for name in ('payload.sha256.json', 'nox-p01-owned.txt', 'NOX.P01.Shell.exe'):
                target = slot / name
                report['slots'][label][name] = {
                    'regular': owner.regular(target),
                    'bytes': target.stat().st_size if owner.regular(target) else None}
    # Real E06 #42132227949: original rollback returned HOLD, but the
    # postmortem's three-code filter rejected it before any physical snapshot.
    # Observe only pre-existing owned slot metadata and the original return
    # code; never claim user-data preservation or rerun Setup.
    if failure['reason'] == 'T06_ORIGINAL_NSIS_ROLLBACK_NOLOSS_HOLD':
        lifecycle = failure.get('installer_lifecycle')
        rollback = lifecycle.get('rollback') if type(lifecycle) is dict else None
        original_code = rollback.get('code') if type(rollback) is dict else None
        installed_slot = report['slots']['installed']
        report['rollback_diagnostic'] = {
            'status': 'DIAGNOSTIC_ONLY_NOT_ACCEPTED',
            'original_exit_code': original_code if type(original_code) is int else None,
            'restored_slot_present': installed_slot['directory'],
            'previous_slot_present': report['slots']['previous']['directory'],
            'saved_slot_present': report['slots']['rollback_saved']['directory'],
            'restored_owner_marker_present': (
                installed_slot['nox-p01-owned.txt']['regular']
                if installed_slot['directory'] else False),
            'user_data_no_loss_accepted': False,
            'release_accepted': False}
        # B03 G4: only a genuine failed rollback has a rollback_diagnostic.
        # Inspect the existing previous-slot backup read-only. Its verdict
        # never erases original NSIS exit or grants NO-LOSS/release acceptance.
        report['rollback_diagnostic']['attested_backup_verifier'] = (
            readonly_rollback_backup_verifier(
                owner, Path(str(install) + '.__p01_previous')))

    # Real E06 #42119061209/#42120828250 reached an UPDATE backup HOLD.
    # A missing stage was previously undiagnosable here. Inspect only the
    # existing CI-owned backup and the EXACT original read-only reviewer. Do
    # not rebuild, relaunch, fix, remove, accept, or attest pre-update inode.
    if failure['reason'] in (
            'T06_ORIGINAL_NSIS_UPDATE_BACKUP_HOLD',
            'T06_UPDATE_BACKUP_MANIFEST_VERIFY_HOLD'):
        previous = Path(str(install) + '.__p01_previous')
        probe = previous / ('nox-g4-unmanaged-' + env['GITHUB_RUN_ID'] + '.bin')
        owner.require(owner.plain_parents(probe, Path(local.anchor)) and
                      not probe.is_symlink() and
                      not getattr(probe, 'is_junction', lambda: False)(),
                      'T06_NSIS_DIAGNOSTICS_BACKUP_REPARSE_HOLD')
        snapshot = {
            'status': 'DIAGNOSTIC_ONLY_NOT_ACCEPTED',
            'original_reason': failure['reason'],
            'pre_update_user_inode_verified': False,
            'release_accepted': False,
            'first_failure': 'BACKUP_NOT_PRESENT'}
        report['update_backup_diagnostic'] = snapshot
        if previous.is_dir():
            snapshot['first_failure'] = 'USER_PROBE_ABSENT_OR_UNSAFE'
            if owner.regular(probe):
                frozen = probe.lstat()
                if (stat.S_ISREG(frozen.st_mode) and frozen.st_nlink == 1 and
                        frozen.st_ino != 0):
                    try:
                        # An inode read AFTER failure only proves the current
                        # snapshot, never the frozen pre-update NO-LOSS identity.
                        observed = owner.verify_exact_probe_slot(
                            previous, probe.name, b"NOX_G4_UNMANAGED_INSTALL_DATA_NOLOSS\\n",
                            (frozen.st_dev, frozen.st_ino), local)
                        snapshot['first_failure'] = 'NONE_IN_CURRENT_SNAPSHOT'
                        snapshot['manifest_files_checked'] = observed.get(
                            'manifest_files_checked')
                    except RuntimeError as error:
                        reason = str(error)
                        snapshot['first_failure'] = (
                            reason if re.fullmatch(
                                r'T06_EXACT_PROBE_SLOT_[A-Z0-9_]+_HOLD',
                                reason) else 'OWNER_SNAPSHOT_VERIFY_HOLD')
                    except (OSError, ValueError):
                        snapshot['first_failure'] = 'BACKUP_PROBE_READ_HOLD'
                else:
                    snapshot['first_failure'] = 'USER_PROBE_INODE_UNSAFE'

        snapshot['attested_backup_verifier'] = readonly_rollback_backup_verifier(owner, previous)
    # Do not run either a failed app or an arbitrary residual script. Admit the
    # existing reviewer's verifier only if it matches its committed Git bytes.
    verifier_rel = 'stage/proposals/P01/C09/Installer/Verify-Payload.ps1'
    verifier = owner.ROOT / verifier_rel
    owner.require(owner.regular(verifier) and
                  owner.plain_parents(verifier, owner.ROOT),
                  'T06_NSIS_DIAGNOSTICS_VERIFIER_PATH_HOLD')
    expected = subprocess.check_output(
        ['git', '-C', str(owner.ROOT), 'show', 'HEAD:' + verifier_rel], timeout=20)
    raw = verifier.read_bytes()
    owner.require(raw == expected or raw.replace(b'\r\n', b'\n') == expected,
                  'T06_NSIS_DIAGNOSTICS_VERIFIER_BYTES_HOLD')
    report['verifier_sha256'] = hashlib.sha256(expected).hexdigest()
    # Two read-only verifier probes distinguish architecture-dependent errors.
    # The original installation result remains failed even if both probes pass.
    powershells = [('native', 'powershell.exe')]
    system = Path(env.get('SystemRoot', r'C:\Windows'))
    wow = system / 'SysWOW64/WindowsPowerShell/v1.0/powershell.exe'
    if system.is_absolute() and owner.plain_parents(wow, Path(system.anchor)) and owner.regular(wow):
        powershells.append(('x86', str(wow)))
    stage = Path(str(install) + '.__p01_stage')
    manifest = stage / 'payload.sha256.json'
    if stage.is_dir() and owner.regular(manifest):
        owner.require(owner.plain_parents(manifest, Path(local.anchor)),
                      'T06_NSIS_DIAGNOSTICS_MANIFEST_PATH_HOLD')
        for architecture, executable in powershells:
            result = owner.run([executable, '-NoProfile', '-NonInteractive',
                '-ExecutionPolicy', 'Bypass', '-File', str(verifier),
                '-Root', str(stage), '-Manifest', str(manifest)], 100)
            report['verifications'].append({'architecture': architecture, **result})
    return report


def main():
    path = Path(__file__).resolve().with_name('t06_samevm_installed_smoke.py')
    spec = importlib.util.spec_from_file_location('nox_existing_t06_smoke', path)
    if spec is None or spec.loader is None:
        raise SystemExit('T06_NSIS_DIAGNOSTICS_OWNER_MISSING')
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    report = collect(owner)
    target = owner.OUTPUT / 'T06_NSIS_FAILURE_DIAGNOSTICS.json'
    owner.require(owner.plain_parents(target, owner.ROOT),
                  'T06_NSIS_DIAGNOSTICS_OUTPUT_PATH_HOLD')
    with target.open('x', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=True, indent=2)
        out.write('\n')
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
